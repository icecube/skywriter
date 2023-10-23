import warnings
import logging

# temporary workaround for https://github.com/icecube/icetray/issues/3112
warnings.filterwarnings(
    "ignore", ".*already registered; second conversion method ignored.", RuntimeWarning
)

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

LOGGER = logging.getLogger("skywriter")
