// native/src/host/host_main.cc
//
// open_stbc_host — embedded-CPython renderer host binary.
// Phase A bring-up: initialize CPython, import sys, print version, exit.
// Subsequent tasks add the bindings module and the main render loop.

#include <Python.h>

#include <cstdio>
#include <cstdlib>

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;

    Py_InitializeEx(/*initsigs=*/1);

    PyObject* sys = PyImport_ImportModule("sys");
    if (!sys) {
        PyErr_Print();
        Py_FinalizeEx();
        return 1;
    }

    PyObject* version = PyObject_GetAttrString(sys, "version");
    if (!version) {
        PyErr_Print();
        Py_DECREF(sys);
        Py_FinalizeEx();
        return 1;
    }

    const char* version_str = PyUnicode_AsUTF8(version);
    std::printf("open_stbc_host: Python %s\n", version_str ? version_str : "<unknown>");

    Py_DECREF(version);
    Py_DECREF(sys);

    if (Py_FinalizeEx() < 0) {
        return 2;
    }
    return 0;
}
