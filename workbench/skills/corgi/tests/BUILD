load("//third_party/bazel_rules/rules_python/python:py_test.bzl", "py_test")

licenses(["notice"])

package(default_visibility = ["//visibility:public"])

py_test(
    name = "renderer_test",
    srcs = ["renderer_test.py"],
    deps = [
        "//configs/users/heykhyati/_agents/skills/corgi/scripts:renderer",
        "//third_party/py/absl/testing:absltest",
    ],
)

py_test(
    name = "validator_test",
    srcs = ["validator_test.py"],
    deps = [
        "//configs/users/heykhyati/_agents/skills/corgi/scripts:validator",
        "//third_party/py/absl/testing:absltest",
    ],
)

py_test(
    name = "corgi_cli_test",
    srcs = ["corgi_cli_test.py"],
    deps = [
        "//configs/users/heykhyati/_agents/skills/corgi/scripts:corgi_lib",
        "//third_party/py/absl/testing:absltest",
        "//third_party/py/yaml",
    ],
)
