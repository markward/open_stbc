"""host_loop module imports cleanly and exposes the public symbols."""


def test_imports():
    from engine import host_loop
    assert hasattr(host_loop, "run")
    assert isinstance(host_loop.SHIP_GATE_MISSION, str)
    assert host_loop.SHIP_GATE_MISSION == "Custom.Tutorial.Episode.M1Basic.M1Basic"


def test_renderer_module_exposes_bindings():
    from engine import renderer
    for name in ("init", "shutdown", "frame", "load_model",
                 "create_instance", "set_world_transform", "set_camera"):
        assert hasattr(renderer, name)


def test_run_M1_Basic_for_a_few_ticks():
    import os
    from pathlib import Path
    import pytest

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    GALAXY_NIF = PROJECT_ROOT / "game" / "data" / "Models" / "Ships" / "Galaxy" / "Galaxy.nif"
    if not GALAXY_NIF.is_file():
        pytest.skip("BC assets not available")

    os.environ["OPEN_STBC_HOST_HEADLESS"] = "1"
    from engine import host_loop
    rc = host_loop.run("Custom.Tutorial.Episode.M1Basic.M1Basic", max_ticks=5)
    assert rc == 0
