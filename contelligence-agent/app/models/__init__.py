"""Pydantic models for the contelligence-agent."""

from app.models.agent_models import (
    AgentEvent,
    EventType,
    InstructOptions,
    InstructRequest,
    InstructResponse,
    ReplyRequest,
)
from app.models.session_models import (
    ConversationTurn,
    SessionEvent,
    SessionEventType,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    ToolCallRecord,
)
from app.models.schedule_models import (
    ActivityEvent,
    CreateScheduleRequest,
    DashboardMetrics,
    ScheduleRecord,
    ScheduleRunRecord,
    TriggerConfig,
    TriggerType,
    UpdateScheduleRequest,
)
from app.models.custom_agent_models import (
    AgentDefinitionRecord,
    AgentSource,
    AgentStatus,
)

__all__ = [
    # Phase 1
    "AgentEvent",
    "EventType",
    "InstructOptions",
    "InstructRequest",
    "InstructResponse",
    "ReplyRequest",
    # Phase 2
    "ConversationTurn",
    "SessionEventType",
    "SessionMetrics",
    "SessionRecord",
    "SessionStatus",
    "ToolCallRecord",
    # Phase 5
    "ActivityEvent",
    "CreateScheduleRequest",
    "DashboardMetrics",
    "ScheduleRecord",
    "ScheduleRunRecord",
    "TriggerConfig",
    "TriggerType",
    "UpdateScheduleRequest",
    # Custom Agent Management
    "AgentDefinitionRecord",
    "AgentSource",
    "AgentStatus",
]