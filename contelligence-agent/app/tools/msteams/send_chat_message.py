"""Tool to send a message to a Teams channel, group chat, or 1:1 chat."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.tool_registry import define_tool
from ._graph_session import get_session

logger = logging.getLogger(f"contelligence-agent.{__name__}")


# ------------------------------------------------------------------
# Sub-models for rich message options
# ------------------------------------------------------------------


class Mention(BaseModel):
    """An @mention to include in the message body.

    The ``display_name`` is inserted into the body as ``<at>display_name</at>``
    at the position indicated by ``placeholder`` (if provided) or appended
    automatically.
    """

    user_id: str = Field(
        ...,
        description="Azure AD object ID of the user to mention.",
    )
    display_name: str = Field(
        ...,
        description="Display name shown for the @mention (e.g. 'Jane Doe').",
    )
    placeholder: str | None = Field(
        None,
        description=(
            "Literal text in the message body to replace with the mention "
            "tag.  E.g. if body contains '{jane}', set placeholder='{jane}'. "
            "If omitted, the mention tag is appended to the body."
        ),
    )


class FileAttachment(BaseModel):
    """A file attachment reference (link to SharePoint / OneDrive)."""

    name: str = Field(
        ...,
        description="Display name of the file (e.g. 'report.pdf').",
    )
    content_url: str = Field(
        ...,
        description="The URL to the file (SharePoint or OneDrive link).",
    )
    content_type: str = Field(
        "reference",
        description=(
            "Attachment content type. Use 'reference' for a SharePoint / "
            "OneDrive file link (default)."
        ),
    )
    id: str | None = Field(
        None,
        description=(
            "Unique ID for the attachment. Auto-generated if omitted."
        ),
    )


class AdaptiveCardAttachment(BaseModel):
    """An Adaptive Card attachment (rich interactive card)."""

    content: dict[str, Any] = Field(
        ...,
        description=(
            "The Adaptive Card JSON payload. Must include '$schema' and "
            "'type': 'AdaptiveCard' at minimum."
        ),
    )
    id: str | None = Field(
        None,
        description="Unique ID for the attachment. Auto-generated if omitted.",
    )


class InlineImage(BaseModel):
    """An inline image to embed directly in the HTML body.

    Graph API uses ``hostedContents`` to upload inline images. The image
    bytes are base64-encoded and referenced in the HTML body via a
    ``<img src=\"../hostedContents/{id}/$value\">`` tag.
    """

    content_bytes_base64: str = Field(
        ...,
        description="Base64-encoded image bytes.",
    )
    content_type: str = Field(
        "image/png",
        description="MIME type of the image (e.g. 'image/png', 'image/jpeg').",
    )
    placeholder: str | None = Field(
        None,
        description=(
            "Literal text in the HTML body to replace with the <img> tag. "
            "If omitted, the image is appended to the body."
        ),
    )


# ------------------------------------------------------------------
# Main parameters model
# ------------------------------------------------------------------


class SendChatMessageParams(BaseModel):
    """Parameters for the msteams_send_chat_message tool.

    Supports three destination types:
      - **Channel**: provide ``team_id`` + ``channel_id``
      - **Chat** (group or 1:1): provide ``chat_id``
    Optionally reply to an existing channel message with ``reply_to_id``.
    """

    # -- Destination (channel vs. chat) --------------------------------

    team_id: str | None = Field(
        None,
        description=(
            "The ID of the team (required for channel messages). "
            "Obtain from msteams_get_teams."
        ),
    )
    channel_id: str | None = Field(
        None,
        description=(
            "The ID of the channel to post to (required for channel "
            "messages). Obtain from msteams_get_channels."
        ),
    )
    chat_id: str | None = Field(
        None,
        description=(
            "The ID of the 1:1 or group chat to send to (required for "
            "chat messages). Obtain from msteams_get_chats."
        ),
    )
    reply_to_id: str | None = Field(
        None,
        description=(
            "Message ID to reply to within a channel thread. Only valid "
            "when sending to a channel (team_id + channel_id). "
            "Obtain from msteams_get_channel_messages."
        ),
    )

    # -- Message content -----------------------------------------------

    body: str = Field(
        ...,
        description=(
            "The message body text. Interpreted as plain text or HTML "
            "depending on content_type."
        ),
    )
    content_type: Literal["text", "html"] = Field(
        "html",
        description=(
            "Body format: 'text' for plain text, 'html' for rich HTML "
            "(supports bold, italic, links, lists, tables, etc.)."
        ),
    )
    subject: str | None = Field(
        None,
        description=(
            "Optional subject / title for the message. Typically used in "
            "channel messages to set the thread subject."
        ),
    )
    importance: Literal["normal", "high", "urgent"] | None = Field(
        None,
        description=(
            "Message importance / priority. 'urgent' sends a priority "
            "notification that repeats every 2 minutes for 20 minutes."
        ),
    )

    # -- Rich content options ------------------------------------------

    mentions: list[Mention] | None = Field(
        None,
        description=(
            "List of @mentions to include. Each mention resolves to a "
            "user by Azure AD object ID and inserts an <at> tag in the body."
        ),
    )
    file_attachments: list[FileAttachment] | None = Field(
        None,
        description=(
            "File attachments (SharePoint / OneDrive links) to include "
            "with the message."
        ),
    )
    adaptive_cards: list[AdaptiveCardAttachment] | None = Field(
        None,
        description=(
            "Adaptive Card attachments for rich interactive content "
            "(buttons, forms, data tables, etc.)."
        ),
    )
    inline_images: list[InlineImage] | None = Field(
        None,
        description=(
            "Inline images to embed in the HTML body. Requires "
            "content_type='html'. Images are uploaded as hostedContents."
        ),
    )

    # -- Browser settings ----------------------------------------------

    headless: bool = Field(
        True,
        description="Launch the browser in headless mode.",
    )

    # -- Validation ----------------------------------------------------

    @model_validator(mode="after")
    def _validate_destination(self) -> SendChatMessageParams:
        has_channel = bool(self.team_id and self.channel_id)
        has_chat = bool(self.chat_id)
        if not has_channel and not has_chat:
            raise ValueError(
                "Provide either (team_id + channel_id) for a channel message "
                "or chat_id for a 1:1 / group chat message."
            )
        if has_channel and has_chat:
            raise ValueError(
                "Provide only one destination: (team_id + channel_id) for a "
                "channel message OR chat_id for a chat message, not both."
            )
        if self.reply_to_id and not has_channel:
            raise ValueError(
                "reply_to_id is only valid for channel messages "
                "(team_id + channel_id)."
            )
        return self


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_graph_body(params: SendChatMessageParams) -> dict[str, Any]:
    """Assemble the Graph API request body from tool parameters."""
    body_content = params.body
    graph_body: dict[str, Any] = {}

    # -- Mentions -------------------------------------------------------
    mentions_payload: list[dict[str, Any]] = []
    if params.mentions:
        for idx, m in enumerate(params.mentions):
            mention_id = idx
            at_tag = f'<at id="{mention_id}">{m.display_name}</at>'
            if m.placeholder and m.placeholder in body_content:
                body_content = body_content.replace(m.placeholder, at_tag, 1)
            else:
                body_content += f" {at_tag}"
            mentions_payload.append({
                "id": mention_id,
                "mentionText": m.display_name,
                "mentioned": {
                    "user": {
                        "id": m.user_id,
                        "displayName": m.display_name,
                        "userIdentityType": "aadUser",
                    },
                },
            })

    # -- Inline images (hostedContents) ---------------------------------
    hosted_contents: list[dict[str, Any]] = []
    if params.inline_images:
        for idx, img in enumerate(params.inline_images):
            content_id = f"inlineImage{idx}"
            img_tag = (
                f'<img src="../hostedContents/{content_id}/$value" '
                f'alt="inline image {idx}" />'
            )
            if img.placeholder and img.placeholder in body_content:
                body_content = body_content.replace(
                    img.placeholder, img_tag, 1,
                )
            else:
                body_content += f" {img_tag}"
            hosted_contents.append({
                "@microsoft.graph.temporaryId": content_id,
                "contentBytes": img.content_bytes_base64,
                "contentType": img.content_type,
            })

    # -- Body -----------------------------------------------------------
    graph_body["body"] = {
        "contentType": params.content_type,
        "content": body_content,
    }

    # -- Optional top-level fields --------------------------------------
    if params.subject:
        graph_body["subject"] = params.subject
    if params.importance:
        graph_body["importance"] = params.importance
    if mentions_payload:
        graph_body["mentions"] = mentions_payload
    if hosted_contents:
        graph_body["hostedContents"] = hosted_contents

    # -- File attachments -----------------------------------------------
    attachments: list[dict[str, Any]] = []
    if params.file_attachments:
        for idx, fa in enumerate(params.file_attachments):
            attachments.append({
                "id": fa.id or str(idx),
                "contentType": fa.content_type,
                "contentUrl": fa.content_url,
                "name": fa.name,
            })
    if params.adaptive_cards:
        for idx, ac in enumerate(params.adaptive_cards):
            attachments.append({
                "id": ac.id or str(1000 + idx),
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": ac.content,
            })
    if attachments:
        graph_body["attachments"] = attachments

    return graph_body


def _graph_path(params: SendChatMessageParams) -> str:
    """Return the Graph endpoint path based on the destination."""
    if params.chat_id:
        return f"/me/chats/{params.chat_id}/messages"
    # Channel message (possibly a reply)
    base = f"/teams/{params.team_id}/channels/{params.channel_id}/messages"
    if params.reply_to_id:
        return f"{base}/{params.reply_to_id}/replies"
    return base


# ------------------------------------------------------------------
# Tool definition
# ------------------------------------------------------------------


@define_tool(
    name="msteams_send_chat_message",
    description=(
        "Send a message to a Microsoft Teams channel, group chat, or 1:1 "
        "chat via the MS Graph API. Supports plain text and HTML bodies, "
        "@mentions, file attachments (SharePoint/OneDrive links), Adaptive "
        "Card attachments, inline images, message importance/urgency, "
        "thread subjects, and replies to existing channel messages. "
        "For channels, provide team_id + channel_id (from msteams_get_teams "
        "and msteams_get_channels). For 1:1 or group chats, provide chat_id "
        "(from msteams_get_chats). To reply in a channel thread, also pass "
        "reply_to_id (from msteams_get_channel_messages)."
    ),
    parameters_model=SendChatMessageParams,
)
async def send_chat_message(
    params: SendChatMessageParams, context: dict,
) -> dict[str, Any]:
    """Send a message to a Teams channel or chat."""
    try:
        session = await get_session(headless=params.headless)

        path = _graph_path(params)
        graph_body = _build_graph_body(params)

        data = await session.graph_post(path, body=graph_body)

        # Build a normalized response
        result: dict[str, Any] = {
            "success": True,
            "messageId": data.get("id"),
            "createdDateTime": data.get("createdDateTime"),
            "webUrl": data.get("webUrl"),
        }

        if params.chat_id:
            result["chatId"] = params.chat_id
            result["destination"] = "chat"
        else:
            result["teamId"] = params.team_id
            result["channelId"] = params.channel_id
            result["destination"] = "channel"
            if params.reply_to_id:
                result["replyToId"] = params.reply_to_id
                result["destination"] = "channel_reply"

        return result

    except Exception as exc:
        logger.exception("msteams_send_chat_message failed")
        return {"error": str(exc)}
