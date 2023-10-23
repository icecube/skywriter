"""Helper script to extract CausalQTot and MJD data from i3 to h5."""

import argparse
import json
from functools import partial

import os
from pathlib import Path
from typing import List, Optional, Final

# temporary workaround for https://github.com/icecube/icetray/issues/3112
# from skywriter import suppress_warnings  # type: ignore[import] # noqa: F401

from skywriter.logging_utils import LOGGER  # type: ignore[import]
from wipac_dev_tools import logging_tools


# try old-style import for CI
from icecube.icetray import I3Tray  # type: ignore[import]

# from I3Tray import I3Tray  # type: ignore[import]


from icecube import (  # type: ignore[import] # noqa: F401
    MuonGun,
    VHESelfVeto,
    astro,
    dataclasses,
    gulliver,
    icetray,
    recclasses,
    simclasses,
    trigger_splitter,
)
from icecube.filterscripts import (  # type: ignore[import]
    alerteventfollowup,
    filter_globals,
)
from icecube.full_event_followup import (  # type: ignore[import]
    frame_packet_to_i3live_json,
    i3live_json_to_frame_packet,
)

# Activate to dump C++ I3 logging to console output.
# icetray.logging.console()


def get_uid(frame):
    uid = (
        frame["I3EventHeader"].run_id,
        frame["I3EventHeader"].event_id,
        frame["I3EventHeader"].sub_event_id,
    )
    return uid


def alertify(frame):
    uid = get_uid(frame)

    LOGGER.info(f"{uid} - Alertify pending {frame.Stop} frame...")

    # Since "SplitUncleanedInIcePulses" is always deleted in the tray
    # the original P-frame will be skipped.
    if "SplitUncleanedInIcePulses" not in frame:
        LOGGER.info(
            f"{uid} - SplitUncleanedInIcePulses is not in pending frame. Skipping what is likely the original P-frame."
        )
        return False

    if isinstance(
        frame["I3SuperDST"], dataclasses.I3RecoPulseSeriesMapApplySPECorrection
    ):
        LOGGER.info(
            f"{uid} - It seems like I3SuperDST is an instance of I3RecoPulseSeriesMapApplySPECorrection... converting to I3SuperDST."
        )
        frame["I3SuperDST_tmp"] = frame["I3SuperDST"]
        del frame["I3SuperDST"]
        frame["I3SuperDST"] = dataclasses.I3SuperDST(
            dataclasses.I3RecoPulseSeriesMap.from_frame(frame, "I3SuperDST_tmp")
        )

    LOGGER.info(f"{uid} - Alertify done.")


def fill_key(frame, source_pframe, key, default_value) -> None:
    if key in frame:
        LOGGER.debug(f"Key {key} already in frame. Skipping.")
    elif key in source_pframe:
        LOGGER.debug(f"Copying key {key} from source P-frame.")
        frame[key] = source_pframe[key]
    else:
        LOGGER.debug(f"Setting {key} to dummy value.")
        frame[key] = default_value


def fill_missing_keys(frame, source_pframes):
    """The realtime code to generate the JSON event expects a certain set of keys in the source frame.
    Keys are copied from the original pframe (if one is available for the pending event and if it has the pending key), otherwise they are set to dummy values.
    """
    uid = get_uid(frame)

    LOGGER.info(f"{uid} - Filling missing keys for {frame.Stop} frame.")

    pframe = source_pframes[uid]

    process_key = partial(fill_key, frame, pframe)

    process_key(filter_globals.EHEAlertFilter, icetray.I3Bool(True))

    for key in [
        "OnlineL2_SplineMPE",
        "OnlineL2_SPE2itFit",
        "OnlineL2_BestFit",
        "PoleEHEOpheliaParticle_ImpLF",
    ]:
        process_key(key, dataclasses.I3Particle())

    for key in [
        "OnlineL2_SplineMPE_CramerRao_cr_zenith",
        "OnlineL2_SplineMPE_CramerRao_cr_azimuth",
        "OnlineL2_BestFit_CramerRao_cr_zenith",
        "OnlineL2_BestFit_CramerRao_cr_azimuth",
    ]:
        process_key(key, dataclasses.I3Double(0))

    for key in [
        "OnlineL2_SplineMPE_MuE",
        "OnlineL2_SplineMPE_MuEx",
        "OnlineL2_BestFit_MuEx",
    ]:
        dummy_particle = dataclasses.I3Particle()
        dummy_particle.energy = 0
        process_key(key, dummy_particle)

    for key in ["OnlineL2_SPE2itFitFitParams", "OnlineL2_BestFitFitParams"]:
        process_key(key, gulliver.I3LogLikelihoodFitParams())

    process_key("OnlineL2_BestFit_Name", dataclasses.I3String("dummy"))

    process_key("PoleEHESummaryPulseInfo", recclasses.I3PortiaEvent())

    for key in ["IceTop_SLC_InTime", "IceTop_HLC_InTime"]:
        process_key(key, icetray.I3Bool(False))


def restore_content(frame, src, keys):
    # The following keys gave serialization errors when trying to copy all keys to the output.
    UNSUPPORTED_KEYS: Final[List[str]] = [
        "EHEDSTShieldParameters_ImpLF",
        "EHEDSTShieldParameters_SPE12",
    ]

    uid = get_uid(frame)
    pframe = src[uid]
    for key in keys:
        if key not in pframe:
            raise RuntimeError(
                f"Required key {key} is not in {pframe.Stop} frame for event {uid}"
            )

        # This check could be done before reaching this point of the code.
        if key in UNSUPPORTED_KEYS:
            raise RuntimeError(f"Required key {key} is not serializable.")
        if pframe.get_stop(key) != icetray.I3Frame.Physics:
            raise RuntimeError(
                f"Required key {key} belongs to {pframe.get_stop(key)} frame, not to Physics frame."
            )

        # In principle we may not want to overwrite existing keys.
        # if key is in frame:
        #   print(f"Key {key} is already in frame, skipping")
        # but right now "alertify" creates dummy keys before this module is run.
        # We should likely split out the filling with empty keys from alertify.
        LOGGER.debug(f"Copying key {key}")
        # This should work as long as it is read-only.
        frame[key] = pframe[key]


def write_json(frame, pframes, extra_particles, output_dir: Path, filenames: List):
    uid = get_uid(frame)

    LOGGER.info(f"{uid} - Writing JSON file...")

    pnf = frame_packet_to_i3live_json(
        i3live_json_to_frame_packet(
            frame[filter_globals.alert_candidate_full_message].value, pnf_framing=False
        ),
        pnf_framing=True,
    )
    msg = json.loads(frame[filter_globals.alert_candidate_full_message].value)
    pnfmsg = json.loads(pnf)
    fullmsg = {
        key: value
        for (key, value) in (list(msg.items()) + list(pnfmsg.items()))
        if key != "frames"
    }

    # The following logic allows to add the coordinates of additional I3Particles
    # to the JSON output.
    event_time_mjd = frame["I3EventHeader"].start_time.mod_julian_day_double
    extra_namer = {"OnlineL2_SplineMPE": "ol2_mpe"}

    for i3particle_key in extra_particles:
        particle = pframes[uid][i3particle_key]
        ra, dec = astro.dir_to_equa(
            particle.dir.zenith,
            particle.dir.azimuth,
            event_time_mjd,
        )
        fullmsg[extra_namer.get(i3particle_key, i3particle_key)] = {
            "ra": ra.item(),
            "dec": dec.item(),
        }

    # The following logic allows to extract the MC truth.
    if "I3MCTree" in frame:
        prim = dataclasses.get_most_energetic_inice(frame["I3MCTree"])
        muhi = dataclasses.get_most_energetic_muon(frame["I3MCTree"])
        ra, dec = astro.dir_to_equa(
            prim.dir.zenith,
            prim.dir.azimuth,
            event_time_mjd,
        )

        fullmsg["true"] = {"ra": ra.item(), "dec": dec.item(), "eprim": prim.energy}

        if muhi is not None:
            fullmsg["true"]["emuhi"] = muhi.energy
        else:
            fullmsg["true"]["emuhi"] = 0

        edep = 0
        if "MMCTrackList" in frame:
            for track in MuonGun.Track.harvest(
                frame["I3MCTree"], frame["MMCTrackList"]
            ):
                intersections = VHESelfVeto.IntersectionsWithInstrumentedVolume(
                    frame["I3Geometry"], track
                )
                for entrance in intersections[::2]:
                    l0 = (entrance - track.pos) * track.dir
                    e0 = track.get_energy(l0) if l0 > 0 else track.get_energy(0)
                    e1 = 0
                    for exit in intersections[1::2]:
                        l1 = (exit - track.pos) * track.dir
                        e1 = track.get_energy(l1)
                    edep += e0 - e1
        fullmsg["true"]["emuin"] = edep

    jf = f'{fullmsg["unique_id"]}.sub{uid[2]:03}.json'
    with open(output_dir / jf, "w") as f:
        json.dump(fullmsg, f)
        LOGGER.info(f"{uid} - Wrote {jf} to directory `{output_dir}`")
        filenames.append(jf)


def extract_pframes(i3files):
    pframes: dict = {}

    def get_frame(frame):
        uid = get_uid(frame)
        LOGGER.info(f"Extracting event {uid}")
        pframes[uid] = frame

    tray = I3Tray()
    tray.Add("I3Reader", Filenamelist=i3files)
    tray.Add(get_frame)
    tray.Execute()

    return pframes


def i3_to_json(
    i3s: List[str],
    extra: List[str],
    basegcd: str,
    output_dir: Path,
    out: str,
    nframes: Optional[int],
) -> List[str]:
    """Convert I3 file to JSON realtime format"""

    filenames: List[str] = []

    pframes = extract_pframes(i3files=i3s)

    LOGGER.info(f"Extracted {len(pframes)} P-frames from input file.")

    tray = I3Tray()
    tray.Add("I3Reader", Filenamelist=i3s)

    # Delete SplitUncleanedInIcePulses, if present, and (re)create it
    # by running the trigger splitter module.
    tray.Add(
        "Delete",
        Keys=["SplitUncleanedInIcePulses", "SplitUncleanedInIcePulsesTimeRange"],
    )

    tray.AddModule(
        "I3TriggerSplitter",
        "InIceSplit",
        TrigHierName="DSTTriggers",
        InputResponses=["InIceDSTPulses"],
        OutputResponses=["SplitUncleanedInIcePulses"],
    )

    # Converts I3SuperDST to the proper format.
    tray.Add(alertify, If=lambda f: get_uid(f) in pframes)

    # Retrieves the keys from the original P frame.
    tray.Add(
        fill_missing_keys, source_pframes=pframes, If=lambda f: get_uid(f) in pframes
    )

    # Why the if `filter_globals.EHEAlertFilter`?
    # Only run on frames where fill_missing_keys was successful.
    # This corresponds to the P matching "uid" in the original I3 file.

    def notify(frame, pframes):
        uid = get_uid(frame)
        if uid in pframes:
            LOGGER.info(f"{uid} - Running AlertEventFollowup")
        else:
            LOGGER.warning(f"{uid} - Skipping sub-event not in original P-frame.")

    tray.Add(notify, "notify-AlertEventFollowup", pframes=pframes)

    tray.Add(
        alerteventfollowup.AlertEventFollowup,
        base_GCD_path=os.path.dirname(basegcd),
        base_GCD_filename=os.path.basename(basegcd),
        If=lambda f: filter_globals.EHEAlertFilter in f,
    )

    tray.Add(
        write_json,
        pframes=pframes,
        extra_particles=extra,
        output_dir=output_dir,
        filenames=filenames,
        If=lambda f: filter_globals.EHEAlertFilter in f,
    )

    if out != "":
        tray.AddModule(
            "I3Writer",
            "writer",
            filename=out,
            streams=[icetray.I3Frame.Physics, icetray.I3Frame.DAQ],
        )

    if nframes is None:
        tray.Execute()
    else:
        tray.Execute(nframes)
    tray.Finish()

    return filenames


def main():
    parser = argparse.ArgumentParser(
        description="Convert I3 file to JSON realtime format"
    )

    parser.add_argument("i3s", nargs="+", help="input i3s")
    parser.add_argument(
        "--basegcd",
        default="/data/user/followup/baseline_gcds/baseline_gcd_136897.i3",
        type=str,
        help="baseline gcd file for creating the GCD diff",
    )
    parser.add_argument(
        "--nframes", type=int, default=None, help="number of frames to process"
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="extra I3Particles to pull out from original i3 file",
    )

    parser.add_argument("-o", "--out", default="", help="output I3 file")
    args = parser.parse_args()

    logging_tools.log_argparse_args(args, logger=LOGGER, level="DEBUG")

    i3_to_json(
        i3s=args.i3s,
        extra=args.extra,
        basegcd=args.basegcd,
        output_dir=Path("."),
        out=args.out,
        nframes=args.nframes,
    )


if __name__ == "__main__":
    main()
