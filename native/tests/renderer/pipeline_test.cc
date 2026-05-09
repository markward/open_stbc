// native/tests/renderer/pipeline_test.cc
#include <gtest/gtest.h>

#include <renderer/pipeline.h>
#include <renderer/window.h>

namespace {

class PipelineTest : public ::testing::Test {
protected:
    std::unique_ptr<renderer::Window> w;
    void SetUp() override {
        try {
            w = std::make_unique<renderer::Window>(64, 64, "pipeline-test", false);
        } catch (const std::runtime_error& e) {
            GTEST_SKIP() << "no GL context: " << e.what();
        }
    }
};

TEST_F(PipelineTest, OpaqueShaderCompilesAndLinks) {
    renderer::Pipeline p;
    EXPECT_NE(p.opaque_shader().program(), 0u);
}

}  // namespace
