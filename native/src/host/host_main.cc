// native/src/host/host_main.cc

#include <Python.h>

#include "host_bindings.h"

#include <cstdio>
#include <cstdlib>

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;

    if (PyImport_AppendInittab("_open_stbc_host", PyInit__open_stbc_host) != 0) {
        std::fprintf(stderr, "open_stbc_host: PyImport_AppendInittab failed\n");
        return 1;
    }

    Py_InitializeEx(/*initsigs=*/1);

    PyObject* mod = PyImport_ImportModule("_open_stbc_host");
    if (!mod) {
        PyErr_Print();
        Py_FinalizeEx();
        return 1;
    }
    Py_DECREF(mod);

    PyObject* sys = PyImport_ImportModule("sys");
    PyObject* version = PyObject_GetAttrString(sys, "version");
    const char* version_str = PyUnicode_AsUTF8(version);
    std::printf("open_stbc_host: Python %s, _open_stbc_host imported\n",
                version_str ? version_str : "<unknown>");
    Py_DECREF(version);
    Py_DECREF(sys);

    if (Py_FinalizeEx() < 0) {
        return 2;
    }
    return 0;
}
