"""Unit tests for TGAction, TGSequence, TGScriptAction."""
import sys
import types
import pytest
import App
from engine.appc.actions import (
    TGAction, TGSequence, TGSequence_Create,
    TGScriptAction, TGScriptAction_Create,
    TGNullAction, TGAction_CreateNull,
    TGTimedAction, TGSoundAction, TGSoundAction_Create,
    TGActionManager, TGObjPtrEvent, TGObjPtrEvent_Create,
    TGAction_Cast,
)


# ── TGAction base ──────────────────────────────────────────────────────────────

def test_action_initially_not_playing():
    a = TGAction()
    assert not a.IsPlaying()


def test_action_play_marks_not_playing_after_completion():
    a = TGAction()
    a.Play()
    assert not a.IsPlaying()


def test_action_completed_fires_registered_events():
    fired = []
    mod = types.ModuleType("_test_action_cb")
    mod.on_done = lambda obj, ev: fired.append(ev.GetEventType())
    sys.modules["_test_action_cb"] = mod

    a = TGAction()
    ev = App.TGEvent_Create()
    ev.SetEventType(App.ET_ACTION_COMPLETED)
    ev.SetDestination(App.g_kTGActionManager)
    a.AddCompletedEvent(ev)
    App.g_kTGActionManager.AddPythonFuncHandlerForInstance(
        App.ET_ACTION_COMPLETED, "_test_action_cb.on_done"
    )
    a.Completed()

    assert App.ET_ACTION_COMPLETED in fired
    del sys.modules["_test_action_cb"]
    App.g_kTGActionManager.RemoveHandlerForInstance(
        App.ET_ACTION_COMPLETED, "_test_action_cb.on_done"
    )


def test_action_completed_clears_events():
    a = TGAction()
    ev = App.TGEvent_Create()
    a.AddCompletedEvent(ev)
    a.Completed()
    # Second call should not fire again (list is cleared)
    a.Completed()  # must not raise


def test_null_action_play_does_nothing():
    null = TGAction_CreateNull()
    null.Play()  # must not raise
    assert not null.IsPlaying()


# ── TGSequence ─────────────────────────────────────────────────────────────────

def test_sequence_create_returns_sequence():
    s = TGSequence_Create()
    assert isinstance(s, TGSequence)


def test_sequence_add_action_increments_count():
    s = TGSequence_Create()
    s.AddAction(TGAction_CreateNull())
    assert s.GetNumActions() == 1


def test_sequence_play_runs_all_actions():
    played = []
    mod = types.ModuleType("_test_seq_cb")
    mod.cb = lambda pAction: played.append(True)
    sys.modules["_test_seq_cb"] = mod

    s = TGSequence_Create()
    s.AddAction(TGScriptAction_Create("_test_seq_cb", "cb"))
    s.AddAction(TGScriptAction_Create("_test_seq_cb", "cb"))
    s.Play()

    assert len(played) == 2
    del sys.modules["_test_seq_cb"]


def test_sequence_add_action_with_dependency_args():
    s = TGSequence_Create()
    dep = TGAction_CreateNull()
    a = TGScriptAction_Create("_test_seq_cb", "cb")
    s.AddAction(a, dep, 1.0)  # must not raise; dependency/delay ignored in Phase 1
    assert s.GetNumActions() == 1


def test_sequence_append_action():
    s = TGSequence_Create()
    s.AppendAction(TGAction_CreateNull())
    assert s.GetNumActions() == 1


def test_sequence_play_completes_self():
    s = TGSequence_Create()
    s.Play()
    assert not s.IsPlaying()


# ── TGScriptAction ─────────────────────────────────────────────────────────────

def test_script_action_create():
    a = TGScriptAction_Create("os.path", "join", "a", "b")
    assert isinstance(a, TGScriptAction)


def test_script_action_play_calls_function():
    called = []
    mod = types.ModuleType("_test_script_action")
    mod.handler = lambda pAction, x: called.append(x)
    sys.modules["_test_script_action"] = mod

    a = TGScriptAction_Create("_test_script_action", "handler", 42)
    a.Play()

    assert called == [42]
    del sys.modules["_test_script_action"]


def test_script_action_play_passes_self_as_first_arg():
    received = []
    mod = types.ModuleType("_test_script_action2")
    mod.handler = lambda pAction: received.append(pAction)
    sys.modules["_test_script_action2"] = mod

    a = TGScriptAction_Create("_test_script_action2", "handler")
    a.Play()

    assert received[0] is a
    del sys.modules["_test_script_action2"]


def test_script_action_missing_module_does_not_raise():
    a = TGScriptAction_Create("no.such.module", "func")
    a.Play()  # must not raise


def test_script_action_missing_func_does_not_raise():
    mod = types.ModuleType("_test_script_action3")
    sys.modules["_test_script_action3"] = mod

    a = TGScriptAction_Create("_test_script_action3", "no_such_func")
    a.Play()  # must not raise

    del sys.modules["_test_script_action3"]


def test_script_action_has_obj_id():
    a = TGScriptAction_Create("m", "f")
    assert isinstance(a.GetObjID(), int)


# ── TGObjPtrEvent ──────────────────────────────────────────────────────────────

def test_obj_ptr_event_roundtrip():
    ev = TGObjPtrEvent_Create()
    action = TGAction()
    ev.SetObjPtr(action)
    assert ev.GetObjPtr() is action


def test_obj_ptr_event_is_tgevent():
    from engine.appc.events import TGEvent
    ev = TGObjPtrEvent_Create()
    assert isinstance(ev, TGEvent)


# ── TGAction_Cast ──────────────────────────────────────────────────────────────

def test_tgaction_cast_returns_action():
    a = TGScriptAction_Create("m", "f")
    assert TGAction_Cast(a) is a


def test_tgaction_cast_non_action_returns_none():
    assert TGAction_Cast(object()) is None


# ── App-level wiring ───────────────────────────────────────────────────────────

def test_app_tgsequence_create():
    assert isinstance(App.TGSequence_Create(), TGSequence)


def test_app_tgscript_action_create():
    a = App.TGScriptAction_Create("os", "getcwd")
    assert isinstance(a, TGScriptAction)


def test_app_tgaction_create_null():
    assert isinstance(App.TGAction_CreateNull(), TGNullAction)


def test_app_g_ktg_action_manager_exists():
    assert isinstance(App.g_kTGActionManager, TGActionManager)


def test_app_tgobjptr_event_create():
    assert isinstance(App.TGObjPtrEvent_Create(), TGObjPtrEvent)


def test_tgobject_get_tgobject_ptr_roundtrip():
    a = TGScriptAction_Create("m", "f")
    obj_id = a.GetObjID()
    result = App.TGObject_GetTGObjectPtr(obj_id)
    assert result is a
