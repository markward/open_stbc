#version 330 core
in  vec2 v_uv;
in  float v_t;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform vec4      u_color;

void main() {
    // Sample the beam texture along U (length, tiled) × V (width).
    vec4 t = texture(u_texture, v_uv);
    // Fade only the target-side endpoint — beam start is anchored to
    // the ship's hardpoint so it must read as solid all the way to the
    // emitter.  Use v_t (untiled 0..1) so the fade stays at the actual
    // target end regardless of texture tile count.
    float endpoint_fade = 1.0 - smoothstep(0.95, 1.0, v_t);
    frag_color = t * u_color;
    frag_color.a *= endpoint_fade;
}
