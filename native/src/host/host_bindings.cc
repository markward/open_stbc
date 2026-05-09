// native/src/host/host_bindings.cc
//
// pybind11 module exposing the renderer host API to Python. Built as both:
//   1. A standalone Python extension module (_open_stbc_host.so) for pytest.
//   2. Statically linked into open_stbc_host (registered via
//      PyImport_AppendInittab before Py_InitializeEx).
//
// Phase A: init/shutdown stubs only. Phases B-E populate the rest of the API.

#include "host_bindings.h"

#include <pybind11/pybind11.h>

#include <string>

namespace py = pybind11;

namespace {

bool g_initialized = false;

void init(int width, int height, const std::string& title) {
    (void)width;
    (void)height;
    (void)title;
    g_initialized = true;
}

void shutdown() {
    g_initialized = false;
}

bool should_close() {
    return false;  // Phase A stub; Window class wires this in Phase B.
}

}  // namespace

PYBIND11_MODULE(_open_stbc_host, m) {
    m.doc() = "open_stbc renderer host bindings (Phase A: stubs)";
    m.def("init", &init, py::arg("width"), py::arg("height"), py::arg("title"),
          "Initialize host (window + GL context in Phase B+).");
    m.def("shutdown", &shutdown, "Tear down host.");
    m.def("should_close", &should_close, "Return true when window close is requested.");
}
