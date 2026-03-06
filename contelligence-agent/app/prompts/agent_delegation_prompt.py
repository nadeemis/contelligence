"""Dynamic delegation prompt section builder.

Generates the system-prompt fragment that lists the agents available
for delegation in a given session.  Called by
``PersistentAgentService._build_system_prompt()`` at session creation time.

Phase: Custom Agent Management
"""

from __future__ import annotations

from app.agents.models import AgentDefinition


def build_delegation_prompt_section(
    agents: dict[str, AgentDefinition],
) -> str:
    """Build the delegation section of the system prompt.

    Called by PersistentAgentService when creating a session. The output
    is appended to the base system prompt.

    Parameters
    ----------
    agents:
        Mapping of agent-id → AgentDefinition for agents available in this
        session.  An empty dict means no agents are configured.

    Returns
    -------
    A Markdown-formatted string to append to the system prompt.
    """
    if not agents:
        return (
            "\n\n## Agent Delegation\n"
            "No specialist agents are configured for this session. "
            "Handle all tasks directly using the atomic tools and Azure MCP Server."
        )

    lines = [
        "\n\n## Agent Delegation",
        "You can delegate specialized subtasks to these focused agents:",
        "",
    ]

    for agent_id, defn in agents.items():
        tool_summary = ", ".join(defn.tools[:4])
        if len(defn.tools) > 4:
            tool_summary += f" +{len(defn.tools) - 4} more"
        lines.append(
            f"- **{defn.display_name}** (`{agent_id}`): {defn.description} "
            f"[Tools: {tool_summary}]"
        )

    lines.extend([
        "",
        "### Delegation Rules",
        "- Delegate when a subtask matches an agent's specialty",
        "- **The sub-agent runs in an isolated session with NO access to your conversation**",
        "- Provide the agent with a clear, self-contained instruction including:",
        "  - The specific task and expected output format",
        "  - All constraints, rules, or validation criteria",
        "  - References to the context_data keys where input data can be found",
        "- **MANDATORY: Pass ALL relevant data in context_data**, including:",
        "  - File contents you have already extracted (PDF text, DOCX content, etc.)",
        "  - Query results from earlier tool calls (search results, Cosmos queries, etc.)",
        "  - Any intermediate analysis or summaries you have produced",
        "  - File paths, blob references, or identifiers the sub-agent may need",
        "- Structure context_data with descriptive keys (e.g., 'invoice_text', 'vendor_data')",
        "- Parent session context is auto-injected as a safety net, but always pass key data explicitly",
        "- After receiving the agent's result, integrate it into your overall response",
        "- If delegation fails, handle the task directly using atomic tools",
        "- Use ONLY agents from the list above — do not invent agent names",
        "",
        "### When NOT to Delegate",
        "- Simple, single-tool operations (just call the tool directly)",
        "- Tasks that require cross-cutting context you've already assembled",
        "- When the user's instruction is straightforward and doesn't need specialization",
    ])

    return "\n".join(lines)
