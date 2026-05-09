#version 330 core

in vec3 v_normal_ws;
in vec2 v_uv;

uniform sampler2D u_base_color;
uniform vec3 u_diffuse_color;
uniform vec3 u_ambient_light;
uniform vec3 u_dir_light_dir_ws;  // direction *toward the light*, normalized
uniform vec3 u_dir_light_color;

out vec4 frag_color;

void main() {
    vec3 n = normalize(v_normal_ws);
    float ndotl = max(dot(n, normalize(u_dir_light_dir_ws)), 0.0);
    vec4 tex = texture(u_base_color, v_uv);
    vec3 lit = (u_ambient_light + ndotl * u_dir_light_color) * u_diffuse_color * tex.rgb;
    frag_color = vec4(lit, 1.0);
}
