add_library(open_stbc_audio STATIC
    wav.cc
)
target_include_directories(open_stbc_audio PUBLIC ${CMAKE_SOURCE_DIR}/native/src)
target_compile_features(open_stbc_audio PUBLIC cxx_std_20)

# Test executable, built only when OPEN_STBC_BUILD_TESTS is on (set by default
# in native/CMakeLists.txt for local builds).
if(OPEN_STBC_BUILD_TESTS)
    add_executable(test_wav tests/test_wav.cc)
    target_link_libraries(test_wav PRIVATE open_stbc_audio)
    add_test(NAME test_wav COMMAND test_wav)
endif()
