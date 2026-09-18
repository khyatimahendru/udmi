load("//learning/gemini/agents/skill_rules:skills.bzl", "agent_skill")
load("//learning/gemini/agents/skills/skill_creator/scripts:skill_defs.bzl", "validate_skill_test")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

validate_skill_test(
    name = "validate_corgi_skill_test",
    with_mdformat = False,
)

agent_skill(
    name = "corgi",
    srcs = [
        "SKILL.md",
    ] + glob(["references/*.md"]),
    scripts = [
        "//configs/users/heykhyati/_agents/skills/corgi/scripts:corgi_cli",
    ],
)
