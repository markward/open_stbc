"""After Task 4, no LensFlare row may appear in the stub-call profile.

This exercises the same MakeLensFlare path that the gameloop harness
records — calling it directly avoids needing a full mission init."""
import App
from engine.appc.sets import SetClass
from engine.appc.planet import Sun


def test_make_lens_flare_records_no_stubs():
    App._stub_tracker.clear()
    App._stub_tracker.set_mission("regression")

    pSet = SetClass()
    pSun = Sun(radius=4040.0, model_path="data/Textures/SunBase.tga")
    pSun.SetWorldLocation((0.0, 0.0, 0.0))
    pSet.AddObjectToSet(pSun, "Sun")

    # Inlined MakeLensFlare equivalent — call the App-level surface so any
    # remaining _NamedStub fall-through is caught.
    pLensFlare = App.LensFlare_Create(pSet)
    pLensFlare.SetSource(pSun, 6)
    pLensFlare.AddFlare(8,  "data/textures/rays.tga",       0.0,  0.2, 0.5, 0.1)
    pLensFlare.AddFlare(30, "data/textures/whiteloop.tga",  0.0,  0.075)
    pLensFlare.AddFlare(30, "data/textures/whiteloop.tga", -0.5,  0.015)
    pLensFlare.AddFlare(30, "data/textures/white2.tga",     0.45, 0.005)
    pLensFlare.AddFlare(30, "data/textures/whitelines.tga", 0.55, 0.015)
    pLensFlare.AddFlare(6,  "data/textures/rays.tga",       0.8,  0.001)
    pLensFlare.AddFlare(30, "data/textures/white2.tga",     0.95, 0.038)
    pLensFlare.AddFlare(30, "data/textures/whiteloop.tga",  1.4,  0.03)
    pLensFlare.AddFlare(30, "data/textures/rainbowloop.tga", 1.6, 0.105)
    pLensFlare.Build()

    App._stub_tracker.reset_mission()
    leaked = {
        name for (name, _, _) in App._stub_tracker.report()
        if name.startswith("LensFlare")
    }
    assert leaked == set(), (
        "Lens-flare SDK calls still hit _NamedStub: " + repr(leaked))
