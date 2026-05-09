#include "gl_fixture.h"

#include <glad/glad.h>
#include <GLFW/glfw3.h>

#include <atomic>
#include <mutex>

namespace assets_test {

namespace {

std::mutex       g_mutex;
GLFWwindow*      g_window = nullptr;
std::atomic<bool> g_probed{false};
std::atomic<bool> g_available{false};

void create_window_locked() {
    glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
#ifdef __APPLE__
    glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GLFW_TRUE);
#endif
    g_window = glfwCreateWindow(1, 1, "assets_tests offscreen", nullptr, nullptr);
}

}  // namespace

bool GLContext::Available() {
    if (g_probed.load()) return g_available.load();
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_probed.load()) return g_available.load();

    if (!glfwInit()) {
        g_probed = true;
        return false;
    }
    create_window_locked();
    if (!g_window) {
        glfwTerminate();
        g_probed = true;
        return false;
    }

    glfwMakeContextCurrent(g_window);
    if (!gladLoadGLLoader(reinterpret_cast<GLADloadproc>(glfwGetProcAddress))) {
        glfwDestroyWindow(g_window);
        g_window = nullptr;
        glfwTerminate();
        g_probed = true;
        return false;
    }
    glfwMakeContextCurrent(nullptr);

    g_probed = true;
    g_available = true;
    return true;
}

void GLContext::SetUp() {
    if (!Available()) GTEST_SKIP() << "no GL context available (headless?)";
    std::lock_guard<std::mutex> lock(g_mutex);
    glfwMakeContextCurrent(g_window);
}

void GLContext::TearDown() {
    std::lock_guard<std::mutex> lock(g_mutex);
    glfwMakeContextCurrent(nullptr);
}

}  // namespace assets_test
