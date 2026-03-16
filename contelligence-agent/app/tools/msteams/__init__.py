"""Microsoft Graph / Teams tools for chat, channel, and calendar integration."""

from __future__ import annotations

from .list_chats import list_chats
from .get_chat_messages import get_chat_messages
from .list_teams import list_teams
from .list_channels import list_channels
from .get_channel_messages import get_channel_messages
from .get_channel_message_replies import get_channel_message_replies
from .list_team_members import list_team_members
from .list_calendar_events import list_calendar_events
from .send_chat_message import send_chat_message
from .send_channel_message import send_channel_message

MSTEAMS_TOOLS = [
    list_chats,
    get_chat_messages,
    list_teams,
    list_channels,
    get_channel_messages,
    get_channel_message_replies,
    list_team_members,
    list_calendar_events,
    send_chat_message,
    send_channel_message,
]
