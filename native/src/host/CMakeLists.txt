# native/src/host/CMakeLists.txt — renderer host binary + pybind11 module.

add_executable(open_stbc_host
    host_main.cc
)

target_link_libraries(open_stbc_host
    PRIVATE
        Python3::Python
)

target_compile_features(open_stbc_host PRIVATE cxx_std_20)

set_target_properties(open_stbc_host PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
