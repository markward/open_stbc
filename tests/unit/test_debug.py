import logging
import time
import App
from engine.appc.debug import (
    CPyDebug, TGProfilingInfo,
    TGProfilingInfo_EnableProfiling, TGProfilingInfo_DisableProfiling,
    TGProfilingInfo_IsProfilingEnabled,
    TGProfilingInfo_StartTiming, TGProfilingInfo_StopTiming,
    TGProfilingInfo_GetTotalTime, TGProfilingInfo_ResetTimings,
)


# ── CPyDebug ─────────────────────────────────────────────────────────────────

def test_cpy_debug_construct_with_module_name():
    d = CPyDebug("Bridge.PowerDisplay")
    assert d.GetName() == "Bridge.PowerDisplay"


def test_cpy_debug_construct_no_args_uses_default_logger():
    d = CPyDebug()
    assert d.GetName() == "open_stbc.cpy_debug"


def test_cpy_debug_print_emits_via_logging(caplog):
    """SDK pattern: debug = App.CPyDebug(__name__).Print; debug("msg")."""
    d = CPyDebug("test.module")
    with caplog.at_level(logging.INFO, logger="test.module"):
        d.Print("hello world")
    assert "hello world" in caplog.text


def test_cpy_debug_print_chain_pattern():
    """SDK pattern: App.CPyDebug(__name__).Print is bound to a local
    `debug` callable; subsequent debug("msg") must invoke Print."""
    d = CPyDebug("ai.module")
    fn = d.Print
    fn("debug line")  # must not raise


def test_cpy_debug_single_call_form():
    """SDK pattern: App.CPyDebug().Print(text) — construct + Print inline."""
    CPyDebug().Print("one-shot")  # must not raise


# ── TGProfilingInfo ─────────────────────────────────────────────────────────

def setup_function(_):
    TGProfilingInfo_ResetTimings()
    TGProfilingInfo_EnableProfiling()


def test_profiling_enabled_by_default():
    """Headless harness benefits from profiling visibility."""
    assert TGProfilingInfo_IsProfilingEnabled() == 1


def test_disable_then_enable():
    TGProfilingInfo_DisableProfiling()
    assert TGProfilingInfo_IsProfilingEnabled() == 0
    TGProfilingInfo_EnableProfiling()
    assert TGProfilingInfo_IsProfilingEnabled() == 1


def test_start_timing_returns_int_id():
    tid = TGProfilingInfo_StartTiming("test::op")
    assert isinstance(tid, int)
    assert tid > 0
    TGProfilingInfo_StopTiming(tid)


def test_start_timing_returns_zero_when_disabled():
    TGProfilingInfo_DisableProfiling()
    try:
        assert TGProfilingInfo_StartTiming("x") == 0
    finally:
        TGProfilingInfo_EnableProfiling()


def test_stop_timing_returns_elapsed_seconds():
    tid = TGProfilingInfo_StartTiming("test::sleep")
    time.sleep(0.01)
    elapsed = TGProfilingInfo_StopTiming(tid)
    assert elapsed >= 0.005  # generous lower bound


def test_stop_timing_unknown_id_returns_zero():
    assert TGProfilingInfo_StopTiming(99999) == 0.0


def test_stop_timing_zero_id_is_no_op():
    """Profiling-disabled StartTiming returns 0; StopTiming(0) must not raise."""
    assert TGProfilingInfo_StopTiming(0) == 0.0


def test_total_time_accumulates_across_calls():
    for _ in range(3):
        tid = TGProfilingInfo_StartTiming("test::accum")
        time.sleep(0.005)
        TGProfilingInfo_StopTiming(tid)
    total = TGProfilingInfo_GetTotalTime("test::accum")
    assert total >= 0.012  # 3 * 0.005 with slack


def test_unique_timing_ids_per_call():
    a = TGProfilingInfo_StartTiming("a")
    b = TGProfilingInfo_StartTiming("b")
    assert a != b
    TGProfilingInfo_StopTiming(a)
    TGProfilingInfo_StopTiming(b)


# ── App namespace ────────────────────────────────────────────────────────────

def test_app_exposes_cpy_debug():
    assert App.CPyDebug is CPyDebug


def test_app_exposes_profiling_module_funcs():
    """SDK pattern: App.TGProfilingInfo_StartTiming etc. used directly."""
    assert App.TGProfilingInfo_StartTiming is TGProfilingInfo_StartTiming
    assert App.TGProfilingInfo_StopTiming is TGProfilingInfo_StopTiming
    assert App.TGProfilingInfo_EnableProfiling is TGProfilingInfo_EnableProfiling


def test_app_exposes_profiling_info_class():
    assert App.TGProfilingInfo is TGProfilingInfo


def test_tg_profiling_info_raii_construction_starts_timing():
    """SDK pattern: kProfiling = App.TGProfilingInfo("MissionLib.X").
    Construction marks timing-start so the named timing is active."""
    TGProfilingInfo_ResetTimings()
    p = TGProfilingInfo("test::raii")
    assert p.GetName() == "test::raii"
    assert p._timing_id > 0  # timing is active


def test_tg_profiling_info_explicit_stop_returns_elapsed():
    p = TGProfilingInfo("test::stop")
    time.sleep(0.005)
    elapsed = p.Stop()
    assert elapsed >= 0.003


def test_tg_profiling_info_stop_is_idempotent():
    p = TGProfilingInfo("test::twice")
    p.Stop()
    assert p.Stop() == 0.0  # second call returns 0


def test_tg_profiling_info_no_name_skips_timing():
    """Bare TGProfilingInfo() with no name is a no-op (no timing started)."""
    p = TGProfilingInfo()
    assert p._timing_id == 0
    assert p.Stop() == 0.0


def test_app_round_trip_via_module():
    """SDK pattern (Effects.py:28):
        iTimingId = App.TGProfilingInfo_StartTiming("Effects::CreateExplosionPuffHigh")
        ...
        App.TGProfilingInfo_StopTiming(iTimingId)
    """
    tid = App.TGProfilingInfo_StartTiming("integration::test")
    assert isinstance(tid, int) and tid > 0
    elapsed = App.TGProfilingInfo_StopTiming(tid)
    assert elapsed >= 0.0
