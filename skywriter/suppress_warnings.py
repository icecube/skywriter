# temporary workaround for https://github.com/icecube/icetray/issues/3112
import warnings

warnings.filterwarnings(
    "ignore", ".*already registered; second conversion method ignored.", RuntimeWarning
)
