add_library(glad STATIC src/glad.c)
target_include_directories(glad PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

if(UNIX)
    target_link_libraries(glad PUBLIC dl)
endif()

# GLAD generated source has unused params + may emit -Wpedantic warnings on some compilers.
target_compile_options(glad PRIVATE -w)
