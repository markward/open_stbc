"""Empirical consumer tracking for TGColorA.

When recording is enabled, every call through a `_NamedStub` whose argument
list contains a TGColorA is recorded with the color values, the caller's
(file, line), and the active mission.  This converts the static "engine
surfaces that accept a color" list into a live "consumers actually reached
by this mission" list.
"""
import App


def _consumer_at(stub_name, color, caller_file, caller_line, mission):
    """Helper: drive the tracker directly so the unit test doesn't depend on
    the _NamedStub plumbing.  Integration with _NamedStub is tested separately
    below."""
    App._color_consumer_tracker.record(stub_name, color, caller_file, caller_line)


def setup_function(_):
    App._color_consumer_tracker.clear()
    App._color_consumer_tracker.disable()


def teardown_function(_):
    App._color_consumer_tracker.clear()
    App._color_consumer_tracker.disable()


def test_disabled_by_default_no_recording():
    App._stub_tracker.set_mission("any")
    color = App.TGColorA(); color.SetRGBA(0.1, 0.2, 0.3, 0.4)
    _consumer_at("ShieldProperty.SetShieldGlowColor", color, "x.py", 1, "any")
    assert App._color_consumer_tracker.report() == []


def test_records_call_when_enabled():
    App._color_consumer_tracker.enable()
    App._stub_tracker.set_mission("m1")
    color = App.TGColorA(); color.SetRGBA(0.1, 0.2, 0.3, 0.4)
    _consumer_at("ShieldProperty.SetShieldGlowColor", color, "ships/Hardpoints/akira.py", 42, "m1")
    rows = App._color_consumer_tracker.report()
    assert len(rows) == 1
    name, mission, caller, rgba, count = rows[0]
    assert name == "ShieldProperty.SetShieldGlowColor"
    assert mission == "m1"
    assert caller == "ships/Hardpoints/akira.py:42"
    assert rgba == (0.1, 0.2, 0.3, 0.4)
    assert count == 1


def test_dedupes_identical_calls_with_count():
    App._color_consumer_tracker.enable()
    App._stub_tracker.set_mission("m1")
    color = App.TGColorA(); color.SetRGBA(1.0, 0.0, 0.0, 1.0)
    for _ in range(5):
        _consumer_at("PhaserProperty.SetInnerCoreColor", color, "p.py", 7, "m1")
    rows = App._color_consumer_tracker.report()
    assert len(rows) == 1
    assert rows[0][-1] == 5


def test_separates_calls_by_mission():
    App._color_consumer_tracker.enable()
    color = App.TGColorA(); color.SetRGBA(0.5, 0.5, 0.5, 1.0)
    App._stub_tracker.set_mission("m1")
    _consumer_at("ShieldProperty.SetShieldGlowColor", color, "h.py", 1, "m1")
    App._stub_tracker.set_mission("m2")
    _consumer_at("ShieldProperty.SetShieldGlowColor", color, "h.py", 1, "m2")
    rows = App._color_consumer_tracker.report()
    missions = sorted(r[1] for r in rows)
    assert missions == ["m1", "m2"]


def test_no_recording_without_mission():
    App._color_consumer_tracker.enable()
    # _stub_tracker._mission is None — outside the harness loop body.
    App._stub_tracker._mission = None
    color = App.TGColorA(); color.SetRGBA(0.1, 0.2, 0.3, 0.4)
    _consumer_at("ShieldProperty.SetShieldGlowColor", color, "x.py", 1, None)
    assert App._color_consumer_tracker.report() == []


def test_namedstub_integration_records_when_called_with_color():
    """A real consumer pathway: `App.Foo.SetShieldGlowColor(color)` via the
    catch-all NamedStub should land in the tracker."""
    App._color_consumer_tracker.enable()
    App._stub_tracker.set_mission("m1")
    color = App.TGColorA(); color.SetRGBA(0.2, 0.4, 0.6, 1.0)
    # Going through the module-level __getattr__ → _NamedStub path
    App.SomeShieldProperty.SetShieldGlowColor(color)  # type: ignore[attr-defined]
    rows = App._color_consumer_tracker.report()
    matching = [r for r in rows if r[0].endswith("SetShieldGlowColor")]
    assert len(matching) == 1
    name, mission, caller, rgba, count = matching[0]
    assert "SetShieldGlowColor" in name
    assert mission == "m1"
    assert rgba == (0.2, 0.4, 0.6, 1.0)
    # caller should point at this test file
    assert "test_color_consumer_tracker.py" in caller


def test_namedstub_ignores_calls_without_color_arg():
    App._color_consumer_tracker.enable()
    App._stub_tracker.set_mission("m1")
    App.SomeProp.SetRange(0.0, 10.0)  # type: ignore[attr-defined]
    assert App._color_consumer_tracker.report() == []


def test_property_databag_setter_records_color_call():
    """Phase 1 has real ShieldProperty etc. with a __getattr__ data-bag setter.
    Color setters on those shims must also land in the tracker — the renderer
    will read them off the shim object in Phase 2."""
    from engine.appc.properties import ShieldProperty
    App._color_consumer_tracker.enable()
    App._stub_tracker.set_mission("m1")
    shield = ShieldProperty("Shield Generator")
    color = App.TGColorA(); color.SetRGBA(0.5, 0.5, 0.7, 0.5)
    shield.SetShieldGlowColor(color)
    rows = App._color_consumer_tracker.report()
    matching = [r for r in rows if "ShieldGlowColor" in r[0]]
    assert len(matching) == 1
    name, mission, caller, rgba, count = matching[0]
    assert "ShieldGlowColor" in name
    assert mission == "m1"
    assert rgba == (0.5, 0.5, 0.7, 0.5)
    assert "test_color_consumer_tracker.py" in caller
