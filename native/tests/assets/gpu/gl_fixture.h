// native/tests/assets/gpu/gl_fixture.h
#pragma once

#include <gtest/gtest.h>

namespace assets_test {

/// Test fixture providing a hidden, offscreen GL 3.3 core context shared
/// across the process lifetime. Skips with a clear message if a context
/// can't be created (e.g. no display, no swrast).
class GLContext : public ::testing::Test {
public:
    static bool Available();

protected:
    void SetUp() override;
    void TearDown() override;
};

}  // namespace assets_test
