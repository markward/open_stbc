###############################################################################
# appc_logger.py - environment diagnostic
# Python 1.5 compatible - runs at module import time
###############################################################################
try:
    import sys

    g_kConfigMapping.SetStringValue("BCEnv", "alive", "1")

    _appc = dir(Appc)
    _n    = len(_appc)
    _s    = _n / 16

    # Last 10 names before each window boundary - fills the alphabetical gaps
    g_kConfigMapping.SetStringValue("BCEnv", "tail02", str(_appc[_s*3-10:_s*3])[:250])
    g_kConfigMapping.SetStringValue("BCEnv", "tail03", str(_appc[_s*4-10:_s*4])[:250])
    g_kConfigMapping.SetStringValue("BCEnv", "tail04", str(_appc[_s*5-10:_s*5])[:250])
    g_kConfigMapping.SetStringValue("BCEnv", "tail12", str(_appc[_s*13-10:_s*13])[:250])
    g_kConfigMapping.SetStringValue("BCEnv", "tail13", str(_appc[_s*14-10:_s*14])[:250])

    g_kConfigMapping.SaveConfigFile("BCEnv.cfg")

except:
    try:
        g_kConfigMapping.SetStringValue("BCEnv", "err",
            str(sys.exc_type) + ": " + str(sys.exc_value))
        g_kConfigMapping.SaveConfigFile("BCEnv.cfg")
    except:
        pass
