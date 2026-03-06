"""run_skill_script — Execute a Python script bundled with a Skill.

Skills can bundle validation, transformation, and computation scripts.
The agent calls this tool to execute them in a sandboxed subprocess.

Phase: Skills Integration
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool


class RunSkillScriptParams(BaseModel):
    skill_name: str = Field(description="Name of the Skill.")
    script_path: str = Field(
        description=(
            "Relative path to the Python script within the Skill's scripts/ "
            "directory. Example: 'scripts/validate_invoice.py'"
        ),
    )
    args: list[str] = Field(
        default_factory=list,
        description=(
            "Command-line arguments to pass to the script. "
            "Typically JSON data strings for processing."
        ),
    )


@define_tool(
    name="run_skill_script",
    description=(
        "Execute a Python script bundled with a Skill. "
        "Use when the Skill instructions reference a script for validation, "
        "transformation, or computation. The script runs in a sandboxed "
        "subprocess with a 30-second timeout. Returns stdout, stderr, and exit code."
    ),
    parameters_model=RunSkillScriptParams,
)
async def run_skill_script_tool(params: RunSkillScriptParams, context: dict) -> dict:
    """Execute a Skill script in a sandboxed subprocess."""
    skills_manager = context.get("skills_manager")
    if skills_manager is None:
        return {"error": "Skills system not available."}

    try:
        result = await skills_manager.run_skill_script(
            params.skill_name,
            params.script_path,
            params.args,
        )
        return result
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Script execution failed: {exc}"}
