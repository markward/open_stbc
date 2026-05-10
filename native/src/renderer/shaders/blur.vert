#version 330 core

// Fullscreen triangle from gl_VertexID — no VBO needed.
// Three vertices produce one large triangle covering the whole viewport.
out vec2 v_uv;

void main() {
    float x = float((gl_VertexID & 1) << 2) - 1.0;
    float y = float((gl_VertexID & 2) << 1) - 1.0;
    v_uv = vec2(x, y) * 0.5 + 0.5;
    gl_Position = vec4(x, y, 0.0, 1.0);
}
