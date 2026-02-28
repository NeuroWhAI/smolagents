#!/usr/bin/env python
# coding=utf-8

# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SKILL_ROOTS = (Path.cwd() / ".smolagents" / "skills", Path.home() / ".smolagents" / "skills")


class SkillError(ValueError):
    """Raised when a skill file is invalid or cannot be loaded safely."""


def _parse_skill_file(content: str) -> tuple[dict[str, Any], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError("Skill file must start with a YAML frontmatter block delimited by '---'.")

    closing_marker_idx = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_marker_idx = idx
            break

    if closing_marker_idx is None:
        raise SkillError("Skill file frontmatter is not properly closed with '---'.")

    raw_frontmatter = "\n".join(lines[1:closing_marker_idx])
    frontmatter = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(frontmatter, dict):
        raise SkillError("Skill frontmatter must be a YAML mapping.")

    body = "\n".join(lines[closing_marker_idx + 1 :]).strip()
    return frontmatter, body


def _iter_resource_files(root_path: Path) -> tuple[str, ...]:
    resources: list[str] = []
    for file_path in root_path.rglob("*"):
        if file_path.is_file() and file_path.name != "SKILL.md":
            resources.append(file_path.relative_to(root_path).as_posix())
    return tuple(sorted(resources))


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    root_path: Path
    body: str
    resources_index: tuple[str, ...]

    @classmethod
    def from_folder(cls, path: str | Path) -> "Skill":
        root_path = Path(path).resolve()
        skill_file = root_path / "SKILL.md"
        if not skill_file.exists():
            raise SkillError(f"Missing SKILL.md in skill directory: {root_path}")

        frontmatter, body = _parse_skill_file(skill_file.read_text(encoding="utf-8"))
        name = frontmatter.get("name")
        description = frontmatter.get("description")

        if not isinstance(name, str) or not name.strip():
            raise SkillError(f"Skill in {root_path} must define a non-empty 'name' in frontmatter.")
        if not isinstance(description, str) or not description.strip():
            raise SkillError(f"Skill '{name}' in {root_path} must define a non-empty 'description' in frontmatter.")

        return cls(
            name=name.strip(),
            description=description.strip(),
            root_path=root_path,
            body=body,
            resources_index=_iter_resource_files(root_path),
        )

    def read_resource(self, path: str) -> str:
        resource_path = Path(path)
        if resource_path.is_absolute():
            raise SkillError("Resource path must be relative to the skill root.")
        if ".." in resource_path.parts:
            raise SkillError("Resource path cannot contain '..'.")

        resolved_root = self.root_path.resolve()
        resolved_target = (resolved_root / resource_path).resolve()

        if not resolved_target.is_relative_to(resolved_root):
            raise SkillError("Resource path escapes the skill root directory.")
        if not resolved_target.exists() or not resolved_target.is_file():
            raise SkillError(f"Skill resource not found: {path}")

        try:
            return resolved_target.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise SkillError(
                f"Skill resource '{path}' is not valid UTF-8 text. Only text resources are supported."
            ) from error

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "root_path": str(self.root_path),
            "body": self.body,
            "resources_index": list(self.resources_index),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            root_path=Path(str(data["root_path"])),
            body=str(data.get("body", "")),
            resources_index=tuple(str(item) for item in data.get("resources_index", [])),
        )


def load_skills(skill_roots: list[str] | None = None) -> list[Skill]:
    roots = [Path(root).expanduser().resolve() for root in skill_roots] if skill_roots is not None else DEFAULT_SKILL_ROOTS

    discovered_skills: list[Skill] = []
    names_to_roots: dict[str, Path] = {}

    for root in roots:
        if not root.exists():
            continue

        for skill_file in sorted(root.rglob("SKILL.md")):
            skill = Skill.from_folder(skill_file.parent)
            previous_root = names_to_roots.get(skill.name)
            if previous_root is not None:
                raise SkillError(
                    f"Duplicate skill name '{skill.name}' found in '{previous_root}' and '{skill.root_path}'."
                )
            names_to_roots[skill.name] = skill.root_path
            discovered_skills.append(skill)

    return sorted(discovered_skills, key=lambda skill: skill.name)


__all__ = ["Skill", "SkillError", "load_skills"]
