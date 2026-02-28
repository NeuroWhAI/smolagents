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

from typing import Any

from .skills import Skill, SkillError
from .tools import Tool


def _error_payload(name: str, error_code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "name": name,
        "error_code": error_code,
        "message": message,
    }


class ActivateSkillTool(Tool):
    name = "activate_skill"
    description = "Loads a skill body and resource tree for a skill name."
    inputs = {"name": {"type": "string", "description": "Name of the skill to activate."}}
    output_type = "object"
    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "name": {"type": "string"},
            "body": {"type": "string"},
            "tree": {"type": "array", "items": {"type": "string"}},
            "error_code": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["ok", "name"],
    }

    def __init__(self, skills: dict[str, Skill]):
        super().__init__()
        self.skills = skills

    def forward(self, name: str) -> dict[str, Any]:
        skill = self.skills.get(name)
        if skill is None:
            return _error_payload(name, "SKILL_NOT_FOUND", f"Skill '{name}' was not found.")

        return {
            "ok": True,
            "name": skill.name,
            "body": skill.body,
            "tree": list(skill.resources_index),
        }


class ReadSkillResourceTool(Tool):
    name = "read_skill_resource"
    description = "Reads one text resource from an activated skill directory by relative path."
    inputs = {
        "name": {"type": "string", "description": "Name of the skill."},
        "path": {"type": "string", "description": "Relative resource path inside the skill root."},
    }
    output_type = "object"
    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "name": {"type": "string"},
            "path": {"type": "string"},
            "content": {"type": "string"},
            "error_code": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["ok", "name"],
    }

    def __init__(self, skills: dict[str, Skill]):
        super().__init__()
        self.skills = skills

    def forward(self, name: str, path: str) -> dict[str, Any]:
        skill = self.skills.get(name)
        if skill is None:
            return _error_payload(name, "SKILL_NOT_FOUND", f"Skill '{name}' was not found.")

        try:
            content = skill.read_resource(path)
        except SkillError as error:
            return _error_payload(name, "RESOURCE_READ_ERROR", str(error))

        return {
            "ok": True,
            "name": skill.name,
            "path": path,
            "content": content,
        }


__all__ = ["ActivateSkillTool", "ReadSkillResourceTool"]
