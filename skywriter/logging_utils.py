import warnings
import logging

# temporary workaround for https://github.com/icecube/icetray/issues/3112
warnings.filterwarnings(
    "ignore", ".*already registered; second conversion method ignored.", RuntimeWarning
)

LOGGER = logging.getLogger("skywriter")
