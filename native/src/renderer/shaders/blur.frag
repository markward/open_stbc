#version 330 core

in vec2 v_uv;

uniform sampler2D u_source;
uniform vec2      u_direction;  // (1,0) = horizontal pass, (0,1) = vertical pass

out vec4 frag_color;

// 9-tap separable Gaussian (sigma ≈ 1.5).  Weights sum to ~1.0.
const float W[9] = float[](0.0162, 0.0540, 0.1216, 0.1945, 0.2270,
                            0.1945, 0.1216, 0.0540, 0.0162);

void main() {
    vec2 texel = u_direction / vec2(textureSize(u_source, 0));
    vec4 result = vec4(0.0);
    for (int i = 0; i < 9; i++) {
        result += texture(u_source, v_uv + texel * float(i - 4)) * W[i];
    }
    frag_color = result;
}
