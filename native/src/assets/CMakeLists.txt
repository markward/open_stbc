add_library(assets STATIC
    src/_placeholder.cc
)
target_include_directories(assets PUBLIC include)
target_compile_features(assets PUBLIC cxx_std_20)
target_link_libraries(assets PUBLIC nif glm glad stb_image)
