# coding=utf-8
# Copyright 2026 HuggingFace Inc.
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

from pathlib import Path

import pytest

from smolagents.skills import Skill, SkillError, load_skills


def _write_skill(folder: Path, name: str = "sample_skill", description: str = "sample skill description") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"""---
name: {name}
description: {description}
---
## Instructions
Use this skill carefully.
""",
        encoding="utf-8",
    )
    return folder


def test_skill_from_folder_and_read_resource(tmp_path):
    skill_dir = _write_skill(tmp_path / "skills" / "sample_skill")
    (skill_dir / "notes.txt").write_text("hello from skill resource", encoding="utf-8")

    skill = Skill.from_folder(skill_dir)

    assert skill.name == "sample_skill"
    assert skill.description == "sample skill description"
    assert "Instructions" in skill.body
    assert skill.resources_index == ("notes.txt",)
    assert skill.read_resource("notes.txt") == "hello from skill resource"


def test_skill_parsing_requires_frontmatter(tmp_path):
    skill_dir = tmp_path / "skills" / "invalid"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("No frontmatter", encoding="utf-8")

    with pytest.raises(SkillError, match="frontmatter"):
        Skill.from_folder(skill_dir)


def test_skill_read_resource_blocks_path_traversal(tmp_path):
    skill_dir = _write_skill(tmp_path / "skills" / "safe_skill", name="safe_skill")
    (skill_dir / "inside.txt").write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("unsafe", encoding="utf-8")
    skill = Skill.from_folder(skill_dir)

    with pytest.raises(SkillError, match=r"\.\."):
        skill.read_resource("../outside.txt")


def test_load_skills_detects_duplicate_names(tmp_path):
    root_one = tmp_path / "root_one"
    root_two = tmp_path / "root_two"

    _write_skill(root_one / "skill_a", name="duplicate_name")
    _write_skill(root_two / "skill_b", name="duplicate_name")

    with pytest.raises(SkillError, match="Duplicate skill name"):
        load_skills([str(root_one), str(root_two)])
