"""Skill tools — the agent's interface to the Skills system.

Provides three tools:
- ``read_skill`` — Load a Skill's full instructions (Level 2)
- ``read_skill_file`` — Load a referenced file from a Skill (Level 3)
- ``run_skill_script`` — Execute a Python script bundled with a Skill
"""

from __future__ import annotations

from .read_skill import read_skill_tool
from .read_skill_file import read_skill_file_tool

SKILL_TOOLS = [read_skill_tool, read_skill_file_tool]
