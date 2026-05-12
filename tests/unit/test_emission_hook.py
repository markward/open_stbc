import tools.mission_harness as mh


def test_install_hook_is_idempotent():
    """Calling install_launch_object_hook() twice replaces the same slot,
    never composes."""
    mh.setup_sdk()
    from engine.appc.emission import install_launch_object_hook, _launch_object
    install_launch_object_hook()
    install_launch_object_hook()
    import Actions.ShipScriptActions as ssa
    assert ssa.LaunchObject is _launch_object


def test_setup_sdk_installs_hook():
    """tools.mission_harness.setup_sdk() should install the hook so the
    gameloop harness gets it automatically."""
    import importlib
    import sys
    import tools.mission_harness as mh

    # Force Actions.ShipScriptActions to be re-imported fresh so we can
    # observe whether setup_sdk re-installs the hook.
    sys.modules.pop("Actions.ShipScriptActions", None)
    sys.modules.pop("Actions", None)

    mh.setup_sdk()
    from engine.appc.emission import _launch_object
    import Actions.ShipScriptActions as ssa
    assert ssa.LaunchObject is _launch_object
