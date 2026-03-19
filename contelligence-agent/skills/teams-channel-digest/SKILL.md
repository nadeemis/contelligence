---
name: teams-channel-digest
description: >
  Summarize recent Microsoft Teams channel messages across one or more teams
  and deliver a formatted daily briefing. Use when asked to "summarize Teams
  channels", "daily Teams digest", "what happened in Teams today", "Teams
  channel briefing", "catch me up on Teams", "unread Teams summary", or when
  automating a daily Teams activity report.
license: MIT
metadata:
  version: 1.0.0
  category: productivity
---

# Teams Channel Digest

A skill for summarizing recent Microsoft Teams channel activity across selected
teams and channels, then delivering a structured daily briefing — either as a
posted Teams message or a saved report.

## When to Use This Skill

- User asks for a summary of recent Teams channel activity
- User wants a daily briefing of what happened in their Teams channels
- User says "catch me up on Teams", "what did I miss in Teams", or similar
- User wants to automate a recurring daily Teams digest
- User needs a written summary of discussions across multiple channels

## Prerequisites

- Access to Microsoft Teams via `msteams_get_teams`, `msteams_get_channels`,
  `msteams_get_channel_messages`
- (Optional) `write_blob` or `local_files` if saving the report to storage
- (Optional) Access to a destination Teams channel if posting the briefing back

## Configuration

Before running, confirm (or ask the user for) the following:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `target_teams` | List of team names to monitor. | `"none"` Ask the user to specify |
| `target_channels` | Channel names to include per team. | `"none"` Ask the user to specify |
| `lookback_hours` | How many hours back to look for messages. | `24` |
| `min_messages` | Minimum number of messages in a channel to include it in the digest. Channels with fewer messages are skipped as inactive. | `1` |
| `delivery_mode` | How to deliver the digest: `"teams"` (post to a channel), `"file"` (save locally), or `"both"`. | `"file"` |
| `delivery_channel` | If `delivery_mode` includes `"teams"`, the name of the team+channel to post the digest to (e.g. `"General > Announcements"`). | none |

---

## Important Constraints

- **ALWAYS CONFIRM** the list of teams and channels to monitor before fetching messages.
- **NEVER** fetch messages from channels the user has not explicitly approved.
- **ALWAYS** filter messages by the specified lookback window and minimum message count to avoid including inactive channels.
- **ALWAYS** summarize based on the actual message content; do not hallucinate or infer information that is not present in the messages.
- **ALWAYS** handle edge cases gracefully, such as channels with no messages, access issues, or messages that contain only attachments.
- **NEVER** include content from private channels or direct messages, as these may contain sensitive information.
- **NEVER** check an existing report for the same period before fetching new messages; always fetch fresh data to ensure the most up-to-date briefing.
- **ALWAYS** ask the user for which teams and channels to include in the digest, even if defaults are set, to ensure you have explicit permission to access those channels.


## Step-by-Step Workflow

### Step 1: Discover Teams and Channels

Retrieve the team listed in `target_teams` (do not fetch any other teams):

```
Tool: msteams_get_teams()
```

For each team listed in `target_teams`, retrieve its channels:

```
Tool: msteams_get_channels(team_id: "<team_id>")
```

Build a list of `(team_name, channel_name, team_id, channel_id)` tuples to process.
Always filter by `target_channels` that are specified.

> **Note:** Fetch teams first, then channels one team at a time — do not
> parallelize Teams API calls, as only one session can be open at a time.

---

### Step 2: Fetch Recent Messages Per Channel

For each `(team_id, channel_id)` pair, fetch the most recent messages:

```
Tool: msteams_get_channel_messages(team_id: "<team_id>", channel_id: "<channel_id>", top: 50)
```

Filter messages client-side to only include those within `lookback_hours` of the
current time. Discard channels where the filtered message count is below
`min_messages`.

For each message, capture:
- **Sender** — display name of the author
- **Timestamp** — when it was sent
- **Body** — text content (strip HTML tags if present)
- **Importance** — `normal`, `high`, or `urgent` (if available)
- **Replies** — reply content and count of replies to this message thread (if available)
- **Reply count** — number of replies to this message thread (if available)

---

### Step 3: Summarize Each Channel

For each active channel (those that passed the `min_messages` filter), produce:

1. **Topic summary** — 2-4 sentences describing the main themes discussed
2. **Key decisions or action items** — bullet list of any decisions made,
   tasks assigned, or follow-ups mentioned
3. **Notable participants** — the 2-3 most active contributors by message count
4. **Sentiment** — overall tone: `positive`, `neutral`, `mixed`, or `urgent`
5. **Message count** — total messages in the lookback window

Use your own reasoning to identify topics, decisions, and action items from
the raw message text. Do not hallucinate — only report what is present in the
messages.

---

### Step 4: Identify Cross-Channel Themes

After summarizing all channels, look across all summaries and identify:

- **Recurring topics** — subjects discussed in 2+ channels
- **Escalations** — any issues marked urgent or that appear in multiple channels
- **Org-wide action items** — tasks or decisions that likely affect multiple teams

---

### Step 5: Compose the Briefing Report

Assemble the final digest using this structure:

```markdown
# 📋 Teams Daily Digest — [Team_Name] › [Channel_Name] — [Date] ([lookback_hours]h window)

## 🔑 Highlights
- [2-5 top-level bullets summarizing the most important activity across all channels]

## 🔁 Cross-Channel Themes
- [bullet per recurring topic or escalation — omit section if none]

## 📣 Channel Summaries

### [Team Name] › [Channel Name]
**Messages:** [N] | **Sentiment:** [sentiment] | **Top contributors:** [names]

[Topic summary paragraph]

**Key decisions / action items:**
- [bullet]
- [bullet]

---
[repeat for each active channel]

## 📊 Activity Snapshot

| Team | Channel | Messages | Sentiment |
|------|---------|----------|-----------|
| ... | ... | ... | ... |

## ℹ️ Coverage
- **Period:** Last [lookback_hours] hours
- **Teams monitored:** [N]
- **Channels monitored:** [N]
- **Channels with activity:** [N]
- **Generated at:** [timestamp UTC]
```

---

### Step 6: Deliver the Briefing

Based on `delivery_mode`:

**If `delivery_mode` includes `"file"`:**

Save the report using `local_files`:

```
Tool: local_files(action: "write",
  path: "~/reports/[channel_name]-teams-digest-YYYY-MM-DD.md",
  content: <report_markdown>)
```
Important! Replace `[channel_name]` with a sanitized version of the channel name or a generic name if multiple channels are included.

**If `delivery_mode` includes `"teams"`:**

Locate the destination team and channel specified in `delivery_channel`, then
post the digest. Because Teams messages have a character limit, post a short
summary (~5 bullets) as the main message, and note that the full report is
saved to file.

```
Tool: (post the summary to the target channel using available Teams messaging tools)
```

**If `delivery_mode` is `"both"`:** Do both of the above.

---

## Edge Cases

| Situation | Handling |
|-----------|----------|
| No messages in lookback window | Report "No activity in the last [N] hours" for that channel |
| Channel access denied | Note it as inaccessible in the Coverage section and continue |
| Message body is empty or contains only attachments | Note "[Attachment or media shared]" as the content |
| HTML in message body | Strip all HTML tags before summarizing |
| Very high message volume (100+) | Summarize the 50 most recent messages; note truncation |
| Single-word or emoji-only messages | Group and count these separately as "reactions / acknowledgements" |
| Bot/system messages | Filter out automated bot messages (sender is a bot) unless they contain meaningful content |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `msteams_get_teams` returns empty list | User may not be in any teams; confirm access and ask user to specify team IDs manually |
| Channel messages return no results | Channel may be empty or access may be restricted; skip and note in report |
| Digest is too long for Teams message | Post only the Highlights + Activity Snapshot sections; attach full report as a file |
| Timestamp filtering removes all messages | The lookback window may be too short; suggest increasing `lookback_hours` |

---

## Example Output

```markdown
# 📋 Teams Daily Digest - Engineering › General and Product › Planning — March 17, 2026 (24h window)

## 🔑 Highlights
- Engineering and Product both discussed the Q2 roadmap; a decision meeting is scheduled for Thursday.
- An urgent production issue was raised in #incidents and escalated to the on-call team.
- Three action items from today's standup were assigned to @alice, @bob, and @carol.
- The design team shared updated mockups for the onboarding flow.

## 🔁 Cross-Channel Themes
- **Q2 Roadmap** — discussed in Engineering > General and Product > Planning
- **Production Incident** — mentioned in Engineering > Incidents and Leadership > Updates

## 📣 Channel Summaries

### Engineering › General
**Messages:** 23 | **Sentiment:** Mixed | **Top contributors:** Alice, Bob, Carlos

The team discussed the upcoming Q2 sprint planning session and reviewed open
pull requests. A debate arose around adopting a new testing framework, with
no final decision reached yet.

**Key decisions / action items:**
- Schedule sprint planning for Wednesday at 10am — @Alice to send invite
- Bob to open a spike ticket for the testing framework evaluation

---

### Engineering › Incidents
**Messages:** 8 | **Sentiment:** Urgent | **Top contributors:** Carlos, On-Call Bot

A production timeout in the payments service was reported at 14:32 UTC.
Carlos escalated to the on-call team. The issue was resolved by 15:10 UTC.

**Key decisions / action items:**
- Post-mortem scheduled for Friday — @Carlos to lead

## 📊 Activity Snapshot

| Team | Channel | Messages | Sentiment |
|------|---------|----------|-----------|
| Engineering | General | 23 | Mixed |
| Engineering | Incidents | 8 | Urgent |
| Product | Planning | 14 | Positive |

## ℹ️ Coverage
- **Period:** Last 24 hours
- **Teams monitored:** 2
- **Channels monitored:** 6
- **Channels with activity:** 3
- **Generated at:** 2026-03-17T23:00:00Z
```

---

## Tips for Best Results

- Run this skill daily at a fixed time (e.g., 8:00 AM) for consistent coverage
- Set `min_messages: 3` to avoid cluttering the digest with low-traffic channels
- For large organizations, scope `target_teams` to only the teams you care about
- The 24-hour default lookback works well for daily digests; use 168 hours (7 days) for a weekly digest
