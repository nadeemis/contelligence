"""Skills integration package.

Provides the ``SkillsManager``, ``SkillStore``, and ``validate_skill_frontmatter``
for runtime Skill management following the Agent Skills specification.
"""

from __future__ import annotations

from app.skills.manager import SkillsManager
from app.skills.store import SkillStore
from app.skills.validator import validate_skill_frontmatter

__all__ = [
    "SkillStore",
    "SkillsManager",
    "validate_skill_frontmatter",
]
