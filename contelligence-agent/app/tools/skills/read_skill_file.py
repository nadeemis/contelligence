"""read_skill_file — Load a referenced file from a Skill (Level 3).

When a Skill's instructions reference additional content in ``references/``,
``scripts/``, or ``assets/``, the agent calls this tool to load that content.

Phase: Skills Integration
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool


class ReadSkillFileParams(BaseModel):
    skill_name: str = Field(description="Name of the Skill.")
    file_path: str = Field(
        description=(
            "Relative path to the file within the Skill directory. "
            "Must be under references/, scripts/, or assets/. "
            "Example: 'references/FIELD_MAPPINGS.md'"
        ),
    )


@define_tool(
    name="read_skill_file",
    description=(
        "Load a referenced file from a Skill's directory. Use this when the "
        "Skill instructions reference additional content in references/, "
        "scripts/, or assets/ subdirectories. Returns the file content."
    ),
    parameters_model=ReadSkillFileParams,
)
async def read_skill_file_tool(params: ReadSkillFileParams, context: dict) -> dict:
    """Load a Level 3 resource file from a Skill."""
    skills_manager = context.get("skills_manager")
    if skills_manager is None:
        return {"error": "Skills system not available."}

    try:
        content = await skills_manager.read_skill_file(params.skill_name, params.file_path)
        return {
            "skill": params.skill_name,
            "file": params.file_path,
            "content": content,
        }
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Failed to read file '{params.file_path}' from skill '{params.skill_name}': {exc}"}
