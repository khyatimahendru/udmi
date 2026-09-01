"""Dynamic skill discovery, YAML frontmatter parsing, and JIT context loader for Mantis."""

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Skill:
    name: str
    description: str
    path: str
    content: str
    is_builtin: bool = False


class SkillManager:
    """Discovers, indexes, and dynamically loads Markdown SKILL.md files."""

    def __init__(self, udmi_root: Optional[str] = None):
        if udmi_root is not None:
            self.udmi_root = os.path.abspath(udmi_root)
        else:
            self.udmi_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self._skills: Dict[str, Skill] = {}
        self.refresh()

    def _parse_skill_file(self, filepath: str, is_builtin: bool = False) -> Optional[Skill]:
        """Parse YAML frontmatter and body from a SKILL.md file."""
        if not os.path.isfile(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except Exception:
            return None

        # Extract frontmatter between --- and ---
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_text, re.DOTALL)
        if not fm_match:
            return None

        frontmatter_text = fm_match.group(1)
        body_content = fm_match.group(2).strip()

        # Parse frontmatter lines (simple YAML parsing)
        name = ""
        description = ""
        for line in frontmatter_text.splitlines():
            line = line.strip()
            if line.startswith("name:"):
                name = line[5:].strip().strip("\"'")
            elif line.startswith("description:"):
                description = line[12:].strip().strip("\"'")

        if not name:
            name = os.path.basename(os.path.dirname(filepath))

        return Skill(
            name=name,
            description=description,
            path=filepath,
            content=body_content,
            is_builtin=is_builtin,
        )

    def refresh(self) -> None:
        """Scan mantis/skills/ and sites/*/skills/ for SKILL.md files."""
        self._skills.clear()

        # 1. Global Built-in Skills: mantis/skills/
        builtin_dir = os.path.join(self.udmi_root, "mantis", "skills")
        if os.path.isdir(builtin_dir):
            for entry in sorted(os.listdir(builtin_dir)):
                skill_file = os.path.join(builtin_dir, entry, "SKILL.md")
                skill = self._parse_skill_file(skill_file, is_builtin=True)
                if skill:
                    self._skills[skill.name] = skill

        # 2. Site-Specific Skills: sites/*/skills/
        sites_dir = os.path.join(self.udmi_root, "sites")
        if os.path.isdir(sites_dir):
            for site_name in sorted(os.listdir(sites_dir)):
                site_skills_dir = os.path.join(sites_dir, site_name, "skills")
                if os.path.isdir(site_skills_dir):
                    for entry in sorted(os.listdir(site_skills_dir)):
                        skill_file = os.path.join(site_skills_dir, entry, "SKILL.md")
                        skill = self._parse_skill_file(skill_file, is_builtin=False)
                        if skill:
                            self._skills[skill.name] = skill

    def list_skills(self) -> List[Dict[str, Any]]:
        """List summary info for all discovered skills."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "path": s.path,
                "is_builtin": s.is_builtin,
            }
            for s in self._skills.values()
        ]

    def get_skill(self, name: str) -> Optional[Skill]:
        """Retrieve a specific skill by name."""
        return self._skills.get(name.strip())

    def match_skills(self, query: str) -> List[Skill]:
        """Match relevant skills based on user instruction or domain terms."""
        q_lower = query.lower()
        matched = []
        for s in self._skills.values():
            if s.name.lower() in q_lower:
                matched.append(s)
            elif any(w in q_lower for w in s.name.lower().split("-")):
                matched.append(s)
            elif any(w in q_lower for w in s.description.lower().split() if len(w) > 4):
                matched.append(s)
        return matched

    def get_system_prompt_catalog(self) -> str:
        """Render a concise skill catalog for system prompt progressive disclosure."""
        if not self._skills:
            return "No skills currently loaded."

        lines = ["## Available Domain Skills Catalog:"]
        for s in self._skills.values():
            tier = "Global Built-in" if s.is_builtin else "Site-Specific"
            lines.append(f"- **`{s.name}`** ({tier}): {s.description}")
        return "\n".join(lines)

    def load_skills_for_context(self, query: str) -> str:
        """Dynamically load the full content of matching skills for JIT injection into prompt."""
        matched = self.match_skills(query)
        if not matched:
            # Default to built-in triage guides if generic query
            matched = list(self._skills.values())[:2]

        blocks = []
        for s in matched:
            blocks.append(f"### Skill Reference: {s.name}\n{s.content}")
        return "\n\n".join(blocks)
