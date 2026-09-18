load("//third_party/bazel_rules/rules_python/python:py_binary.bzl", "py_binary")
load("//third_party/bazel_rules/rules_python/python:py_library.bzl", "py_library")

licenses(["notice"])

package(default_visibility = ["//visibility:public"])

py_library(
    name = "renderer",
    srcs = ["renderer.py"],
)

py_library(
    name = "validator",
    srcs = ["validator.py"],
)

py_library(
    name = "corgi_lib",
    srcs = [
        "__init__.py",
        "corgi_cli.py",
        "renderer.py",
        "validator.py",
    ],
    deps = [
        ":renderer",
        ":validator",
        "//third_party/py/yaml",
    ],
)

py_binary(
    name = "corgi_cli",
    srcs = ["corgi_cli.py"],
    main = "corgi_cli.py",
    deps = [
        ":corgi_lib",
        ":renderer",
        ":validator",
        "//third_party/py/yaml",
    ],
)
