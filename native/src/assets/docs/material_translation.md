# Material Translation Notes

How BC NIF property values map onto the `assets::Material` fields. v1 is
BC-faithful: enum values are stored verbatim and interpreted by the renderer
at draw time.

## NiMaterialProperty

- `ambient/diffuse/specular/emissive` → `Material::ambient/diffuse/specular/emissive`
  (Color3 → glm::vec3; alpha component is carried separately as `Material::alpha`).
- `glossiness` → `Material::glossiness`.

## NiAlphaProperty

`flags` is a packed bitfield (D3D7-era). Decoded as:

| bit(s) | meaning                                |
|-------:|----------------------------------------|
| 0      | alpha-blend enable                     |
| 1-4    | src blend factor (D3DBLEND_*)          |
| 5-8    | dst blend factor (D3DBLEND_*)          |
| 9      | alpha-test enable                      |
| 10-12  | alpha-test func (D3DCMP_*)             |
| 13     | zwrite enable when blended             |

`threshold` → `Material::alpha_test_threshold` (uint8 0–255).

## NiZBufferProperty

`flags`: bit 0 = depth-test enable; bit 1 = depth-write enable; bits 2-4 =
comparison function (D3DCMP_*).

## NiVertexColorProperty

- `vertex_mode` → `Material::vc_source` (replace / multiply / etc.).
- `lighting_mode` → `Material::vc_lighting_mode`.

## NiTexturingProperty → Material::stages

| NIF slot   | StageSlot |
|------------|-----------|
| base       | Base      |
| dark       | Dark      |
| detail     | Detail    |
| gloss      | Gloss     |
| glow       | Glow      |
| bump_map   | Bump      |
| decal0     | Decal0    |
| decal1     | Decal1    |
| decal2     | Decal2    |

`apply_mode` from the NiTexturingProperty propagates into
`TextureStage::apply_mode` for all populated stages (BC has one apply mode
per property, not per stage).

## NiMultiTextureProperty → Material::stages

NiMultiTextureProperty has 5 `MultiTextureElement`s. Their slot mapping is
established empirically. Initial mapping (subject to revision once BC NIFs
that actually use this property are observed during integration testing):

| NMT element index | StageSlot |
|-------------------|-----------|
| 0 | Base   |
| 1 | Dark   |
| 2 | Detail |
| 3 | Glow   |
| 4 | Gloss  |

`apply_mode` for stages built from NiMultiTextureProperty is hardcoded to 2
(APPLY_MODULATE), matching niflib's default for legacy v3.x.
