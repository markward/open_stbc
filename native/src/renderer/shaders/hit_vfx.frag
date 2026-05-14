#version 330 core
in  vec2 v_uv;
out vec4 frag_color;

uniform sampler2D u_texture;
uniform float     u_alpha;

void main() {
    vec4 t = texture(u_texture, v_uv);
    frag_color = vec4(t.rgb, t.a * u_alpha);
}
