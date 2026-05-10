"""Phase-1 light objects: Light + LightPlacement.

BC scripts call:
    kThis = App.LightPlacement_Create(name, set_name, parent)
    kThis.SetTranslateXYZ(x, y, z)
    kThis.AlignToVectors(forward, up)
    kThis.ConfigAmbientLight(r, g, b, dimmer)        # or ConfigDirectionalLight
    kThis.Update(0)

LightPlacement inherits PlacementObject (which inherits ObjectClass) so
SetTranslateXYZ / AlignToVectors / Update / GetWorldRotation come for free.
ConfigAmbientLight / ConfigDirectionalLight materialise a Light into the
containing SetClass._lights list and _lights_by_name index.
"""
from engine.appc.objects import ObjectClass
from engine.appc.placement import PlacementObject


class Light(ObjectClass):
    """Phase-1 light object stored in SetClass._lights and returned by
    GetLight(). Inherits ObjectClass for two reasons:
      1. SDK code treats lights as objects (set membership, naming).
      2. Save/load (deferred) round-trips Light state via the same
         pickling pathway as other Appc objects.
    The unused event-handler / object-id machinery on ObjectClass is
    incidental cost that pays off when those features land.
    """
    KIND_AMBIENT = "ambient"
    KIND_DIRECTIONAL = "directional"

    def __init__(self, kind, name, r, g, b, dimmer):
        super().__init__()
        self.SetName(name)
        self._kind = kind
        self._color = (float(r), float(g), float(b))
        self._dimmer = float(dimmer)
        # Overwritten by LightPlacement.ConfigDirectionalLight or by
        # SetClass.CreateDirectionalLight; harmless default for ambients.
        self._direction_world = (0.0, 1.0, 0.0)
        # Set when this Light was materialised through a LightPlacement;
        # direction_world() then re-reads the placement's forward axis on
        # every call so post-Config rotation changes (e.g. a second
        # AlignToVectors, or animation controllers in future work) flow
        # through. None for the 8-arg pSet.CreateDirectionalLight path,
        # where direction is given directly and no placement exists.
        self._placement: "LightPlacement | None" = None

    def direction_world(self):
        """Resolve current world-space 'where the light shines' direction.

        For LightPlacement-backed lights, queries the placement's
        rotation matrix on each call. For direct-creation lights, returns
        the static value provided at construction.
        """
        if self._placement is not None:
            rot = self._placement.GetWorldRotation()
            fwd = rot.GetRow(1)
            return (fwd.x, fwd.y, fwd.z)
        return self._direction_world

    def AddIlluminatedObject(self, _obj):
        # Phase 1 doesn't filter per-object lighting; every light affects
        # every object in its set. SDK callers chain the result; returning
        # None is fine (their next call would be on the receiver, which
        # they discard via `pLight = pSet.GetLight(...)` reassignment).
        return None


class LightPlacement(PlacementObject):
    def ConfigAmbientLight(self, r, g, b, dimmer):
        self._make_light(Light.KIND_AMBIENT, r, g, b, dimmer)

    def ConfigDirectionalLight(self, r, g, b, dimmer):
        # No need to snapshot the forward at this moment: Light._placement
        # points back at us, and Light.direction_world() re-reads
        # GetWorldRotation().GetRow(1) on every call. This means later
        # AlignToVectors invocations or animation controllers attached to
        # the placement flow through to the renderer without any extra
        # bookkeeping at the call sites.
        self._make_light(Light.KIND_DIRECTIONAL, r, g, b, dimmer)

    def _make_light(self, kind, r, g, b, dimmer):
        light = Light(kind, self.GetName(), r, g, b, dimmer)
        light._placement = self
        if self._containing_set is not None:
            self._containing_set._lights.append(light)
            self._containing_set._lights_by_name[self.GetName()] = light
        return light


def LightPlacement_Create(name, set_name, parent=None):
    p = LightPlacement()
    p.SetName(name)
    import App
    s = App.g_kSetManager.GetSet(set_name)
    if s is not None:
        s.AddObjectToSet(p, name)  # populates p._containing_set
    return p
