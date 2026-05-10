"""Phase-1 backdrop objects: StarSphere + BackdropSphere.

BC scripts call:
    kThis = App.StarSphere_Create()           # opaque starfield
    kThis = App.BackdropSphere_Create()       # alpha-blended overlay

    kThis.SetName(name)
    kThis.SetTranslateXYZ(0, 0, 0)            # always origin; ignored
    kThis.AlignToVectors(forward, up)         # world orientation
    kThis.SetTextureFileName("data/stars.tga")
    kThis.SetTargetPolyCount(256)
    kThis.SetHorizontalSpan(1.0)
    kThis.SetVerticalSpan(1.0)
    kThis.SetSphereRadius(300.0)
    kThis.SetTextureHTile(22.0)
    kThis.SetTextureVTile(11.0)
    kThis.Rebuild()                           # no-op; we evaluate at submit
    pSet.AddBackdropToSet(kThis, name)        # append-order = draw-order
    kThis.Update(0)

The renderer reads stored config via aggregate_for_renderer at the end
of this module and passes a flat list to the C++ side each tick.
"""
from engine.appc.objects import ObjectClass


class Backdrop(ObjectClass):
    """Common storage. Subclasses differ only in their `kind`
    discriminator; the rendering blend mode is selected from kind.

    Inherits ObjectClass so SetTranslateXYZ / AlignToVectors /
    GetWorldRotation come for free, matching how Light / LightPlacement
    inherit from ObjectClass.
    """
    KIND_STAR = "star"
    KIND_BACKDROP = "backdrop"

    def __init__(self, kind):
        super().__init__()
        self._kind = kind
        self._texture_path: str = ""
        self._target_poly_count: int = 256
        self._horizontal_span: float = 1.0
        self._vertical_span: float = 1.0
        self._sphere_radius: float = 300.0
        self._texture_h_tile: float = 1.0
        self._texture_v_tile: float = 1.0

    def SetTextureFileName(self, path):  self._texture_path = str(path)
    def SetTargetPolyCount(self, n):     self._target_poly_count = int(n)
    def SetHorizontalSpan(self, h):      self._horizontal_span = float(h)
    def SetVerticalSpan(self, v):        self._vertical_span = float(v)
    def SetSphereRadius(self, r):        self._sphere_radius = float(r)
    def SetTextureHTile(self, h):        self._texture_h_tile = float(h)
    def SetTextureVTile(self, v):        self._texture_v_tile = float(v)

    def Rebuild(self):
        # In real BC this regenerates the sphere mesh with the configured
        # poly count and UV mapping. We defer all geometry to the
        # renderer (cached & shared per-poly_count across all backdrops),
        # so this is a no-op. Listed explicitly rather than caught by
        # ObjectClass.__getattr__ so the name shows up in code search.
        return None


class StarSphere(Backdrop):
    def __init__(self):
        super().__init__(Backdrop.KIND_STAR)


class BackdropSphere(Backdrop):
    def __init__(self):
        super().__init__(Backdrop.KIND_BACKDROP)


def StarSphere_Create() -> StarSphere:
    return StarSphere()


def BackdropSphere_Create() -> BackdropSphere:
    return BackdropSphere()
