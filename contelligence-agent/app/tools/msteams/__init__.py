"""Microsoft Teams tools — browser-authenticated MS Graph access.

All tools share a single ``TeamsGraphSession`` (see ``_graph_session.py``)
that extracts a Graph bearer token from the user's live Teams browser
session via Playwright + Edge.  No app registrations or client secrets
are required.
"""

from __future__ import annotations

from .get_chats import get_chats
from .get_chat_messages import get_chat_messages
from .get_teams import get_teams
from .get_channels import get_channels
from .get_channel_messages import get_channel_messages
from .get_calendar import get_calendar
from .get_calendar_event import get_calendar_event
from .get_online_meeting import get_online_meeting
from .send_chat_message import send_chat_message

MSTEAMS_TOOLS = [
    get_chats,
    get_chat_messages,
    get_teams,
    get_channels,
    get_channel_messages,
    get_calendar,
    get_calendar_event,
    get_online_meeting,
    send_chat_message,
]
