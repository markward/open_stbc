add_executable(probe_shape_transforms probe_shape_transforms.cc)
target_link_libraries(probe_shape_transforms PRIVATE nif)
if(APPLE)
    target_link_options(probe_shape_transforms PRIVATE
        "LINKER:-force_load,$<TARGET_FILE:nif>")
elseif(UNIX)
    target_link_options(probe_shape_transforms PRIVATE
        "LINKER:--whole-archive"
        "$<TARGET_FILE:nif>"
        "LINKER:--no-whole-archive")
endif()
