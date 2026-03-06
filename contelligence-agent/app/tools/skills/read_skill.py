"""read_skill — Load a Skill's full instructions (Level 2).

When the agent determines a task matches a Skill's description (from the
Level 1 metadata in the system prompt), it calls this tool to load the
full SKILL.md body into context.

Phase: Skills Integration
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool


class ReadSkillParams(BaseModel):
    skill_name: str = Field(
        description="Name of the Skill to load (from the Available Skills list in your system prompt).",
    )


@define_tool(
    name="read_skill",
    description=(
        "Load the full instructions for a Skill. Use this when a task matches "
        "a Skill's description from the Available Skills section. Returns the "
        "complete SKILL.md body with step-by-step workflow, field mappings, "
        "and domain expertise."
    ),
    parameters_model=ReadSkillParams,
)
async def read_skill_tool(params: ReadSkillParams, context: dict) -> dict:
    """Load Level 2 instructions for a named Skill."""
    skills_manager = context.get("skills_manager")
    if skills_manager is None:
        return {"error": "Skills system not available."}

    try:
        content = await skills_manager.get_skill_instructions(params.skill_name)
        return {"skill": params.skill_name, "instructions": content}
    except Exception as exc:
        return {"error": f"Failed to load skill '{params.skill_name}': {exc}"}
