#version 330 core

in vec3 v_pos_local;
in vec2 v_uv;

uniform sampler2D u_texture;
uniform vec2  u_tile;
uniform vec2  u_span;
uniform int   u_use_alpha;   // 0 = opaque (Star), 1 = blended (Backdrop)

out vec4 frag_color;

void main() {
    // Outside the span region the texture should not appear at all (so
    // partial-coverage backdrops like nebulae don't tile across the
    // whole sky). For alpha-blended backdrops we discard; for opaque
    // star spheres span is always 1.0 so the branch never triggers.
    if (v_uv.x > u_span.x || v_uv.y > u_span.y) {
        if (u_use_alpha == 1) discard;
    }
    // Span maps the textured region of the sphere to the full [0,1]
    // texture coordinate range, so the texture's own edge alpha (RGBA
    // backdrops fade to 0 at their borders) produces a smooth blend
    // instead of a razor-sharp discard cutoff. Tile then multiplies on
    // top of that for repeating starfields.
    vec2 uv = vec2(v_uv.x / u_span.x * u_tile.x,
                   v_uv.y / u_span.y * u_tile.y);
    vec4 tex = texture(u_texture, uv);
    if (u_use_alpha == 1) {
        frag_color = vec4(tex.rgb, tex.a);
    } else {
        frag_color = vec4(tex.rgb, 1.0);
    }
}
