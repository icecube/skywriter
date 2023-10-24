<!--- Top of README Badges (automated) --->
[![PyPI](https://img.shields.io/pypi/v/icecube-skywriter)](https://pypi.org/project/icecube-skywriter/) [![GitHub release (latest by date including pre-releases)](https://img.shields.io/github/v/release/icecube/skywriter?include_prereleases)](https://github.com/icecube/skywriter/) [![PyPI - License](https://img.shields.io/pypi/l/icecube-skywriter)](https://github.com/icecube/skywriter/blob/main/LICENSE) [![Lines of code](https://img.shields.io/tokei/lines/github/icecube/skywriter)](https://github.com/icecube/skywriter/) [![GitHub issues](https://img.shields.io/github/issues/icecube/skywriter)](https://github.com/icecube/skywriter/issues?q=is%3Aissue+sort%3Aupdated-desc+is%3Aopen) [![GitHub pull requests](https://img.shields.io/github/issues-pr/icecube/skywriter)](https://github.com/icecube/skywriter/pulls?q=is%3Apr+sort%3Aupdated-desc+is%3Aopen) 
<!--- End of README Badges (automated) --->
# skywriter
Upstream Tools for SkyDriver &amp; the Skymap Scanner.

## I3 to JSON converter
The main tool provided by `skywriter` is the `i3_to_json` converter function and script. The function reads a (list of) I3 file(s), processes them using the the realtime alert followup code (`AlertEventFollowup` module) and writes the events out as JSON files.

As SkyMap Scanner is designed to process the `SplitUncleanedInIcePulses` pulse series, the converter generates it by running the `I3TriggerSplitter` module on the original DAQ (Q) frame, hence creating one or more new Physics (P) frames (one for each "subevent" in the data). If already present, the `SplitUncleanedInIcePulses` object is deleted beforehand. In case of multiple subevents, only the subevent-id corresponding matching the original P-frame is processed.

The `AlertEventFollowup` module expects the Physics I3Frame to have a given set of keys. Such set of keys is currently hardcoded in the converter code. If the keys are present in the original P-frame, the corresponding objects are copied over to the output JSON. If not, they are filled with dummy values. If you plan to use these keys in your own Skymap Scanner reconstruction module make sure they have meaningful values.

Extra `I3Particle` objects, typically corresponding to reconstruction outputs, can be "extracted" through the `--extra` option. This means that the equatorial coordinates are calculated and written out in a JSON branch.

### GCD
In order to produce lightweight payloads, the `AlertEventFollowup` code uses the so called "GCD diff" functionality (sometimes called "GCD compress"). The input GCD is compared against a given "base GCD" and only the difference is stored in the JSON-encoded GCD, along with the filename of the base GCD.

Skymap Scanner will look up a matching filename of the base GCD file in a pre-defined set of locations. In principle, it should not matter much which base GCD is used as long as Skymap Scanner can retrieve it. If you use a custom base GCD you should make sure it is made available to Skymap Scanner.


### Example usage
Assuming you have set up your environment and loaded an IceTray shell, you can run the converter as (for example):
```
python skywriter/i3_to_json.py --extra "OnlineL2_SplineMPE" /data/ana/realtime/alert_catalog_v2/input_files/Level2pass2_IC86.2011_data_Run00118435_Subrun00000000_00000144_event58198553.i3
```
this will use the default base GCD.


### Known limitations
- The converter always writes out JSON files and does not allow to simply obtain JSON-encoded string corresponding to the input event. Yet you may treat output files as ephemeral, and delete them after the scan.
- The converter supports the reading of a sequence of I3 files, but it is mostly tested with a single input file. If you encounter problems with converting multiple files, please file an issue. More in general, rather than producing sets of JSON files for archival, it could be better to do any conversion on-the-fly and track the conversion options in the user code.
- It is not possible to copy an arbitrary key/object from the input P-frame to the output P-frame. There is also no warranty that a particle extracted with the `--extra` option will have a corresponding object in the output P-frame. If you need such a feature, or you want to improve this behavior, feel free to file a pull request!
- Events in the input frame(s) are currently identified by `run_id`, `event_id`, `subevent_id`, which in turn are used to name the output JSON files. There is no warranty that these are unique in simulation events. Note that while Skymap Scanner does not care about the event being scanned having a unique id, SkyDriver currently identifies events by `run_id` and `event_id` only (although in principle, you could still scan different events with identical `run_id` and `event_id`, it is just a matter of bookkeeping and information retrieval). The best approach would be to ensure that sets of simulated events processed with SkyDriver are assigned unique `(run_id, event_id)`.