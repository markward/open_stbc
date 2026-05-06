###############################################################################
# appc_logger.py
#
# Appended to game/scripts/App.py by setup.py.
# Runs inside the App module namespace (UtopiaModule, g_kSystemWrapper,
# g_kConfigMapping all available directly).
#
# Wraps GetGameTime to sample wall time / frame / game time every tick.
# Buffers in memory; flushes to BCTickLog.cfg every 30s via SaveConfigFile
# (C++ file I/O - bypasses whatever blocks Python-level open()).
#
# Python 1.5 compatible: no f-strings, no True/False, no import X as Y.
###############################################################################
try:
    import time

    _time_func = time.clock
    _last_frame = -1
    _ticks = []
    _orig_GetGameTime = UtopiaModule.GetGameTime

    def _flush():
        i = 0
        for line in _ticks:
            g_kConfigMapping.SetStringValue("BCTickLog", "t" + str(i), line)
            i = i + 1
        g_kConfigMapping.SetIntValue("BCTickLog", "count", len(_ticks))
        g_kConfigMapping.SaveConfigFile("BCTickLog.cfg")

    def _on_get_game_time(self):
        global _last_frame, _last_save
        game_time = _orig_GetGameTime(self)
        frame = g_kSystemWrapper.GetUpdateNumber()
        wall = _time_func()
        if frame != _last_frame:
            _ticks.append("%f %d %f" % (wall, frame, game_time))
            _last_frame = frame
            if wall - _last_save >= 30.0:
                _flush()
                _last_save = wall
        return game_time

    _last_save = _time_func()
    UtopiaModule.GetGameTime = _on_get_game_time

except:
    try:
        import sys
        g_kConfigMapping.SetStringValue("BCTickLog", "err_type", str(sys.exc_type))
        g_kConfigMapping.SetStringValue("BCTickLog", "err_value", str(sys.exc_value))
        g_kConfigMapping.SaveConfigFile("BCTickLog.cfg")
    except:
        pass
