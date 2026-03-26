# Contelligence Agent — Tool Reference

This document provides a comprehensive reference for all tools available to the Contelligence agent. Tools are the atomic capabilities the agent uses to carry out instructions — each tool performs a specific action like extracting a document, querying a database, or browsing a web page. The agent autonomously selects and chains tools based on your natural language instructions.


> 📌 Additional tools and integrations are in development and will be added over time. This reference is updated regularly to reflect the latest capabilities.
> 
> 
> Contelligence can also be extended with MCP servers and custom tools. For instructions on how to create your own tools and integrate them with Contelligence, see the [Developer Guide](DEVELOPER_GUIDE.md).

---

## Table of Contents

- [Extraction Tools](#extraction-tools) (5)
- [Storage Tools](#storage-tools) (6)
- [AI Tools](#ai-tools) (1)
- [DevOps Tools](#devops-tools) (5)
- [Power BI Tools](#power-bi-tools) (3)
- [Desktop Tools](#desktop-tools) (1)
- [Browser Tools](#browser-tools) (1)
- [Microsoft Teams Tools](#microsoft-teams-tools) (8)
- [SharePoint Tools](#sharepoint-tools) (6)

---

## Extraction Tools

Tools for extracting text, tables, and structured data from documents in various formats. All extraction tools support multiple input sources: raw bytes, base64-encoded content, local filesystem paths, or Azure Blob Storage.

### `extract_pdf`

Extract text, tables, and metadata from PDF files.

Uses PyMuPDF (fitz) for parsing. Supports page filtering, table extraction, image metadata extraction, and output in markdown or structured JSON format.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_bytes` | `bytes` | No | `None` | Raw bytes of the PDF file. Preferred when the caller already has the content in memory. |
| `file_bytes_b64` | `str` | No | `None` | Base64-encoded PDF file content. |
| `local_path` | `str` | No | `None` | Absolute or relative path to a PDF file on the local filesystem. |
| `storage_account` | `str` | No | `None` | Azure Storage account name (authentication uses DefaultAzureCredential). |
| `container` | `str` | No | `None` | Azure Blob Storage container name. |
| `path` | `str` | No | `None` | Blob path to the PDF file. |
| `extract_tables` | `bool` | No | `True` | Whether to extract tables from the PDF. |
| `extract_images` | `bool` | No | `False` | Whether to extract embedded image metadata. |
| `pages` | `str` | No | `None` | Page filter expression. Supports ranges like `1-5` and comma-separated values like `1,3,7`. Omit to process all pages. |
| `format` | `"markdown" \| "json"` | No | `"markdown"` | Output format: `markdown` returns a rendered markdown document, `json` returns structured data. |
| `filename` | `str` | No | `None` | Optional descriptive filename for the result metadata. |

**Source:** `contelligence-agent/app/tools/extraction/extract_pdf.py`

---

### `extract_docx`

Extract text, tables, styles, and metadata from Word DOCX files.

Uses python-docx for parsing. Returns content as markdown (default) or structured JSON with paragraph styles, table data, and document metadata.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_bytes` | `bytes` | No | `None` | Raw bytes of the DOCX file. |
| `file_bytes_b64` | `str` | No | `None` | Base64-encoded DOCX file content. |
| `local_path` | `str` | No | `None` | Absolute or relative path to a DOCX file on the local filesystem. |
| `storage_account` | `str` | No | `None` | Azure Storage account name. |
| `container` | `str` | No | `None` | Azure Blob Storage container name. |
| `path` | `str` | No | `None` | Blob path to the DOCX file. |
| `format` | `"markdown" \| "json"` | No | `"markdown"` | Output format. |
| `filename` | `str` | No | `None` | Optional descriptive filename for the result metadata. |

**Source:** `contelligence-agent/app/tools/extraction/extract_docx.py`

---

### `extract_xlsx`

Extract tabular data from Excel XLSX workbooks.

Uses openpyxl to read sheets, headers, and rows. Supports filtering by sheet name and output as markdown tables or structured JSON.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_bytes` | `bytes` | No | `None` | Raw bytes of the XLSX file. |
| `file_bytes_b64` | `str` | No | `None` | Base64-encoded XLSX file content. |
| `local_path` | `str` | No | `None` | Absolute or relative path to an XLSX file on the local filesystem. |
| `storage_account` | `str` | No | `None` | Azure Storage account name. |
| `container` | `str` | No | `None` | Azure Blob Storage container name. |
| `path` | `str` | No | `None` | Blob path to the XLSX file. |
| `sheets` | `str` | No | `None` | Comma-separated sheet names to extract. Omit to extract all sheets. |
| `format` | `"markdown" \| "json"` | No | `"markdown"` | Output format. |
| `filename` | `str` | No | `None` | Optional descriptive filename for the result metadata. |

**Source:** `contelligence-agent/app/tools/extraction/extract_xlsx.py`

---

### `extract_pptx`

Extract slide content from PowerPoint PPTX files.

Uses python-pptx to read titles, text, speaker notes, and shape types from each slide. Returns content as markdown or structured JSON.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_bytes` | `bytes` | No | `None` | Raw bytes of the PPTX file. |
| `file_bytes_b64` | `str` | No | `None` | Base64-encoded PPTX file content. |
| `local_path` | `str` | No | `None` | Absolute or relative path to a PPTX file on the local filesystem. |
| `storage_account` | `str` | No | `None` | Azure Storage account name. |
| `container` | `str` | No | `None` | Azure Blob Storage container name. |
| `path` | `str` | No | `None` | Blob path to the PPTX file. |
| `format` | `"markdown" \| "json"` | No | `"markdown"` | Output format. |
| `filename` | `str` | No | `None` | Optional descriptive filename for the result metadata. |

**Source:** `contelligence-agent/app/tools/extraction/extract_pptx.py`

---


## Storage Tools

Tools for reading, writing, and querying data across Azure Blob Storage, Azure AI Search, and Azure Cosmos DB.

### `read_blob`

Read from Azure Blob Storage.

Supports three actions: list containers or blobs (with optional prefix filter), download file content as text, or retrieve blob properties/metadata. Use `list` to discover what files exist before processing them.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `storage_account` | `str` | No | `None` | Azure Storage account name. Uses the default when omitted. |
| `container` | `str` | No | `None` | Blob Storage container name. If omitted with `action='list'`, lists containers instead. |
| `action` | `"list" \| "read" \| "metadata"` | **Yes** | — | Action to perform. |
| `path` | `str` | No | `None` | Blob path within the container. Required for `read` and `metadata` actions. |
| `prefix` | `str` | No | `None` | Filter prefix for the `list` action (e.g. `documents/`). |
| `max_results` | `int` | No | `100` | Maximum number of blobs to return when listing. |

**Source:** `contelligence-agent/app/tools/storage/read_blob.py`

---

### `write_blob`

Write content to Azure Blob Storage.

Uploads text content to the specified container and path. Use base64 encoding for binary data. Specify `content_type` for the correct MIME type.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `storage_account` | `str` | No | `None` | Azure Storage account name. Uses the default when omitted. |
| `container` | `str` | **Yes** | — | Blob Storage container name. |
| `path` | `str` | **Yes** | — | Destination blob path within the container. |
| `content` | `str` | **Yes** | — | Text content to write. Use base64 encoding for binary data. |
| `content_type` | `str` | No | `"application/json"` | MIME type of the content being uploaded. |

**Source:** `contelligence-agent/app/tools/storage/write_blob.py`

---

## AI Tools

Tools for AI operations including embeddings generation via Azure OpenAI.

### `generate_embeddings`

Generate vector embeddings for a list of text strings using Azure OpenAI.

Returns one embedding vector per input text. Supports batch processing (automatically chunks into batches of 100) and configurable dimensions. Use this when you need to make content searchable via vector/semantic search, or when creating embeddings for document chunks.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `texts` | `list[str]` | **Yes** | — | List of text strings to generate embeddings for. |
| `model` | `str` | No | `"text-embedding-3-large"` | Azure OpenAI embedding model deployment name. |
| `dimensions` | `int` | No | `1536` | Desired embedding dimensions (model-dependent). `text-embedding-3-large` supports 256, 1024, or 3072. |

**Source:** `contelligence-agent/app/tools/ai/generate_embeddings.py`

---

## DevOps Tools

Tools for interacting with Azure DevOps — work item tracking, project information, and sprint management. All DevOps tools authenticate via a PAT token configured in the environment.

### `devops_get_work_item`

Retrieve a single Azure DevOps work item by ID.

Returns the work item's fields (title, state, assigned to, description, etc.), and optionally its relations and links. Use this when you need details about a specific bug, task, user story, or feature.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `organization` | `str` | No | `None` | Azure DevOps organization name or ID. Uses the configured default when omitted. |
| `project` | `str` | No | `None` | Azure DevOps project name or ID. Uses the configured default when omitted. |
| `work_item_id` | `int` | **Yes** | — | The ID of the work item to retrieve. |
| `fields` | `str` | No | `None` | Comma-separated list of field reference names to return (e.g. `System.Title,System.State`). Omit to return all fields. |
| `expand` | `str` | No | `None` | Expand parameters. Options: `None`, `Relations`, `Fields`, `Links`, `All`. |

**Source:** `contelligence-agent/app/tools/devops/get_work_item.py`

---

### `devops_list_work_items`

Retrieve multiple Azure DevOps work items by their IDs in a single batch (maximum 200).

Use this after a WIQL query to hydrate the returned work item IDs with full field data, or when you already know the specific IDs you need.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `organization` | `str` | No | `None` | Azure DevOps organization name or ID. |
| `project` | `str` | No | `None` | Azure DevOps project name or ID. |
| `ids` | `list[int]` | **Yes** | — | List of work item IDs to retrieve (maximum 200). |
| `fields` | `str` | No | `None` | Comma-separated list of field reference names to return. |
| `expand` | `str` | No | `None` | Expand parameters. Options: `None`, `Relations`, `Fields`, `Links`, `All`. |

**Source:** `contelligence-agent/app/tools/devops/list_work_items.py`

---

### `devops_query_work_items`

Query Azure DevOps work items using WIQL (Work Item Query Language).

Returns matching work item IDs and columns. For flat queries this returns work item references; for tree/one-hop queries it returns link references. Use `devops_list_work_items` afterward to fetch full field data for the returned IDs.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | `str` | **Yes** | — | A WIQL query string. Example: `"Select [System.Id], [System.Title] From WorkItems Where [System.WorkItemType] = 'Bug' AND [System.State] <> 'Closed' order by [System.CreatedDate] desc"` |
| `organization` | `str` | No | `None` | Azure DevOps organization name or ID. |
| `project` | `str` | No | `None` | Azure DevOps project name or ID. |
| `team` | `str` | No | `None` | Team name or ID to scope the query to. |
| `top` | `int` | No | `None` | Maximum number of results to return. Omit for API default. |

**Source:** `contelligence-agent/app/tools/devops/query_work_items.py`

---

### `devops_get_iterations`

List iteration paths (sprints) for an Azure DevOps project or team.

Returns iteration names, paths, start/end dates, and timeframe. Use this to discover sprint boundaries, check the current iteration, or list past/future sprints.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `organization` | `str` | No | `None` | Azure DevOps organization name or ID. |
| `project` | `str` | No | `None` | Azure DevOps project name or ID. |
| `team` | `str` | No | `None` | Team name or ID. When provided, returns only the iterations selected for that team. |
| `timeframe` | `str` | No | `None` | Filter iterations by timeframe. Options: `current`, `past`, `future`. Omit for all. |

**Source:** `contelligence-agent/app/tools/devops/get_iterations.py`

---

### `devops_get_project`

Retrieve Azure DevOps project information.

Returns the project's name, description, state, visibility, and default team. Pass `*` as the project parameter to list all projects in the organization.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `organization` | `str` | No | `None` | Azure DevOps organization name or ID. |
| `project` | `str` | No | `None` | Project name or ID. Pass `*` to list all projects in the organization. |

**Source:** `contelligence-agent/app/tools/devops/get_project.py`

---

## Power BI Tools

Tools for querying Power BI datasets and retrieving schema metadata via the XMLA-backed REST API. Authenticate via the user's Azure AD token.

### `powerbi_execute_dax_query`

Execute a DAX query against a Power BI dataset (semantic model).

Returns tabular results as rows. The query must start with `EVALUATE`. Use this to retrieve report data, aggregations, measures, or ad-hoc analyses. Optionally supports row-level security impersonation.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dataset_id` | `str` | **Yes** | — | The Power BI dataset (semantic model) ID to query. |
| `dax_query` | `str` | **Yes** | — | A DAX query string. Must begin with `EVALUATE`. Example: `"EVALUATE TOPN(10, 'Sales', 'Sales'[Amount], DESC)"` |
| `workspace_id` | `str` | No | `None` | Power BI workspace (group) ID. Uses the configured default when omitted. |
| `impersonated_user` | `str` | No | `None` | UPN of the user to impersonate for row-level security. |

**Source:** `contelligence-agent/app/tools/powerbi/execute_dax_query.py`

---

### `powerbi_get_dataset_tables`

Retrieve table and column metadata from a Power BI dataset.

Uses a multi-strategy approach: REST API tables endpoint (push datasets), Admin Scanning API (all dataset types), or DAX `INFO.COLUMNS()` (XMLA endpoint). Each strategy is tried in order; the first success wins.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dataset_id` | `str` | **Yes** | — | The Power BI dataset (semantic model) ID. |
| `workspace_id` | `str` | No | `None` | Power BI workspace (group) ID. Uses the configured default when omitted. |

**Source:** `contelligence-agent/app/tools/powerbi/get_dataset_tables.py`

---

### `powerbi_list_datasets`

List all datasets (semantic models) in a Power BI workspace.

Returns dataset IDs, names, and configuration details. Use this to discover available datasets before running DAX queries.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `workspace_id` | `str` | No | `None` | Power BI workspace (group) ID. Uses the configured default when omitted. |

**Source:** `contelligence-agent/app/tools/powerbi/list_datasets.py`

---

## Desktop Tools

Tools for interacting with the local filesystem on the user's desktop machine.

### `local_files`

Read, list, or write files on the local desktop filesystem.

Supports listing directory contents (optionally recursive), reading file content as text (with chunked reads via offset/length for large files), and writing/appending text content to files. All paths must be inside the user's home directory for security.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `"list" \| "read" \| "write"` | **Yes** | — | Action to perform. |
| `path` | `str` | **Yes** | — | Absolute or `~`-relative path on the local filesystem. |
| `content` | `str` | No | `None` | Text content to write. Required when `action='write'`. |
| `offset` | `int` | No | `0` | Byte offset to start reading from (only for `action='read'`). |
| `length` | `int` | No | `None` | Maximum number of bytes to read (only for `action='read'`). Defaults to read to end. |
| `append` | `bool` | No | `False` | If true, append content instead of overwriting (only for `action='write'`). |
| `max_results` | `int` | No | `200` | Maximum entries to return when listing a directory. |
| `recursive` | `bool` | No | `False` | If true, list directory contents recursively (only for `action='list'`). |

**Source:** `contelligence-agent/app/tools/desktop/local_files.py`

---

## Browser Tools

Tools for interactive web browsing using a persistent Microsoft Edge session with the user's profile preserved.

### `browse_web`

Browse the web interactively using Microsoft Edge with the user's profile preserved (logins, cookies, extensions).

Launches Edge with a dedicated browser profile seeded from the user's real Edge profile so that existing logins carry over. The browser stays open between calls for multi-step workflows. Supports a wide range of actions for full browser automation.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | `"navigate" \| "click" \| "fill" \| "select" \| "check" \| "uncheck" \| "screenshot" \| "get_text" \| "get_html" \| "wait" \| "hover" \| "press_key" \| "scroll" \| "close"` | **Yes** | — | Action to perform on the page. |
| `url` | `str` | No | `None` | URL to navigate to. Required for `action='navigate'`. |
| `selector` | `str` | No | `None` | CSS or Playwright selector targeting the element. Required for click, fill, select, check, uncheck, hover. Optional for screenshot/get_text/get_html. Supports `text=`, `role=`, `label=`, `placeholder=`, etc. |
| `value` | `str` | No | `None` | Value for the action: text to type (fill), option to select, key to press, or scroll direction (`up`/`down`). |
| `timeout` | `int` | No | `60000` | Timeout in milliseconds for the action. |
| `headless` | `bool` | No | `True` | Whether to run Edge in headless mode. |
| `user_data_dir` | `str` | No | `None` | Path to a custom user-data directory. Omit to use the default `~/.contelligence/browser-profile`. |

**Supported actions:**

| Action | Description |
|--------|-------------|
| `navigate` | Go to a URL |
| `click` | Click an element matched by selector |
| `fill` | Type text into an input/textarea |
| `select` | Choose an option from a `<select>` dropdown |
| `check` / `uncheck` | Toggle a checkbox or radio button |
| `screenshot` | Capture a screenshot of the page or element |
| `get_text` | Extract visible text from the page or element |
| `get_html` | Extract the HTML of the page or element |
| `wait` | Wait for a selector to appear |
| `hover` | Hover over an element |
| `press_key` | Press a keyboard key (e.g. `Enter`, `Tab`) |
| `scroll` | Scroll the page (`up` or `down`) |
| `close` | Close the browser session |

**Source:** `contelligence-agent/app/tools/browser/browse_web.py`

---

## Microsoft Teams Tools

Tools for interacting with Microsoft Teams via the MS Graph API. All Teams tools authenticate by extracting a Graph bearer token from the user's live Microsoft Edge browser session — no app registration or client secrets required.

### `msteams_get_teams`

List all Microsoft Teams the current user has joined.

Returns team IDs, display names, descriptions, archive status, and visibility settings via the MS Graph API (`/me/joinedTeams`).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_teams.py`

---

### `msteams_get_channels`

List all channels in a Microsoft Teams team.

Returns channel IDs, display names, descriptions, and membership types via `/teams/{team_id}/channels`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | `str` | **Yes** | — | The ID of the team. Obtain from `msteams_get_teams`. |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_channels.py`

---

### `msteams_get_channel_messages`

Retrieve messages from a Microsoft Teams channel.

Returns full message bodies, senders, timestamps, replies (threaded), attachments (including adaptive cards), @mentions, reactions, inline images, and system events (app installs, member changes) via `/teams/{team_id}/channels/{channel_id}/messages`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | `str` | **Yes** | — | The ID of the team containing the channel. |
| `channel_id` | `str` | **Yes** | — | The ID of the channel. Obtain from `msteams_get_channels`. |
| `channel_name` | `str` | No | `""` | Display name of the channel (used for browser navigation to capture correct token scopes). |
| `top` | `int` | No | `50` | Maximum number of messages to return (1–50). |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_channel_messages.py`

---

### `msteams_get_chats`

List the current user's Microsoft Teams chats.

Returns chat IDs, topics, chat types, last message previews, and optionally member details via `/me/chats`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `top` | `int` | No | `50` | Maximum number of chats to return (1–50). |
| `filter` | `str` | No | `None` | OData `$filter` expression. Example: `"chatType eq 'oneOnOne'"` for 1:1 chats only. |
| `expand_members` | `bool` | No | `False` | If true, expand the members navigation property. |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_chats.py`

---

### `msteams_get_chat_messages`

Retrieve messages from a specific Microsoft Teams chat.

Returns message bodies, senders, timestamps, attachments, and @mentions via `/me/chats/{chat_id}/messages`. Supports sorting and date-range filtering.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `chat_id` | `str` | **Yes** | — | The ID of the chat. Obtain from `msteams_get_chats`. |
| `top` | `int` | No | `50` | Maximum number of messages to return (1–50). |
| `orderby` | `str` | No | `None` | Sort order: `lastModifiedDateTime desc` or `createdDateTime desc`. |
| `filter` | `str` | No | `None` | OData `$filter` expression for date-range filtering. Must be used with `orderby` on the same property. |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_chat_messages.py`

---

### `msteams_get_calendar`

Retrieve calendar events for the current user.

Returns event subjects, start/end times, organizer, online meeting URLs, and attendees via `/me/calendarView`. Defaults to the next 7 days if no date range is specified.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | `str` | No | `None` | Start of the date range in ISO 8601 format (e.g. `2026-03-17T00:00:00Z`). Defaults to today. |
| `end_date` | `str` | No | `None` | End of the date range in ISO 8601 format. Defaults to 7 days from start. |
| `top` | `int` | No | `50` | Maximum number of events to return (1–100). |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_calendar.py`

---

### `msteams_get_calendar_event`

Retrieve full details of a specific calendar event.

Returns the subject, body, start/end times, location, organizer, attendees with RSVP status, online meeting join URL, recurrence pattern, and attachments via `/me/events/{event_id}`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `event_id` | `str` | **Yes** | — | The ID of the calendar event. Obtain from `msteams_get_calendar`. |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

**Source:** `contelligence-agent/app/tools/msteams/get_calendar_event.py`

---

### `msteams_get_online_meeting`

Retrieve details of a Microsoft Teams online meeting.

Supports lookup by meeting ID, join web URL, or join meeting ID (numeric meeting code). Returns subject, start/end times, participants, lobby settings, join information, and audio conferencing details.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `meeting_id` | `str` | No | `None` | The online-meeting ID. Obtain from the `onlineMeeting` property of a calendar event. |
| `join_web_url` | `str` | No | `None` | The joinWebUrl (Teams 'Join' link). Use when you have the meeting URL but not the ID. |
| `join_meeting_id` | `str` | No | `None` | The joinMeetingId (numeric meeting code). Use when you have the dial-in meeting ID. |
| `headless` | `bool` | No | `True` | Launch the browser in headless mode. |

> Provide exactly one of `meeting_id`, `join_web_url`, or `join_meeting_id`.

**Source:** `contelligence-agent/app/tools/msteams/get_online_meeting.py`

---

## SharePoint Tools

Tools for interacting with SharePoint Online document libraries. Two authentication modes are available: REST API (service-principal or delegated token) and browser-based (Playwright + Edge SSO, no token management).

### `sharepoint_list_document_libraries`

List all document libraries in a SharePoint site via the REST API.

Returns library IDs, titles, item counts, and URLs. Use the library title with `sharepoint_list_items` to browse folders and files.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `site_url` | `str` | No | `None` | Full URL of the SharePoint site (e.g. `https://contoso.sharepoint.com/sites/team`). Overrides the default setting. |

**Source:** `contelligence-agent/app/tools/sharepoint/list_document_libraries.py`

---

### `sharepoint_list_items`

List folders and files inside a SharePoint document library via the REST API.

Navigate into subfolders by providing `folder_path`. Returns file names, sizes, modification dates, and server-relative URLs.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `library_title` | `str` | **Yes** | — | Title of the document library (e.g. `Documents`, `Shared Documents`). |
| `folder_path` | `str` | No | `None` | Server-relative path of a subfolder. Omit to list the library root. |
| `site_url` | `str` | No | `None` | Full URL of the SharePoint site. |

**Source:** `contelligence-agent/app/tools/sharepoint/list_items.py`

---

### `sharepoint_download_file`

Download a file from a SharePoint document library via the REST API.

Returns file metadata (name, size, version) and optionally the file content as a base64-encoded string.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `server_relative_url` | `str` | **Yes** | — | Server-relative URL of the file (e.g. `/sites/team/Shared Documents/Report.pdf`). Obtain from `sharepoint_list_items`. |
| `site_url` | `str` | No | `None` | Full URL of the SharePoint site. |
| `include_content` | `bool` | No | `True` | If true, include the file content as base64. Set to false for metadata only. |

**Source:** `contelligence-agent/app/tools/sharepoint/download_file.py`

---

### `sharepoint_browser_list_document_libraries`

List all document libraries in a SharePoint site using an authenticated browser session (Playwright + Edge).

The browser carries the user's real SSO cookies, so no service-principal or delegated tokens are needed. Returns the same data as `sharepoint_list_document_libraries`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `site_url` | `str` | **Yes** | — | Full URL of the SharePoint site. Required to establish the browser session. |
| `headless` | `bool` | No | `True` | Launch in headless mode. Falls back to headed if authentication requires interactive login. |

**Source:** `contelligence-agent/app/tools/sharepoint/browser_list_document_libraries.py`

---

### `sharepoint_browser_list_items`

List folders and files in a SharePoint document library using an authenticated browser session.

Supports recursive listing up to a configurable depth. Returns file names, sizes, dates, and server-relative URLs.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `library_title` | `str` | **Yes** | — | Title of the document library. |
| `folder_path` | `str` | No | `None` | Server-relative path of a subfolder. Omit to list the library root. |
| `site_url` | `str` | **Yes** | — | Full URL of the SharePoint site. |
| `recursive` | `bool` | No | `False` | If true, recursively list subfolders up to `max_depth` levels. |
| `max_depth` | `int` | No | `3` | Maximum folder depth to recurse into (1–10). |
| `headless` | `bool` | No | `True` | Launch in headless mode. |

**Source:** `contelligence-agent/app/tools/sharepoint/browser_list_items.py`

---

### `sharepoint_browser_download_file`

Download a file from a SharePoint document library using an authenticated browser session (Playwright + Edge).

The browser carries the user's real SSO cookies, so no service-principal or delegated tokens are needed. Returns file metadata and optionally content as base64.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `server_relative_url` | `str` | **Yes** | — | Server-relative URL of the file. |
| `site_url` | `str` | **Yes** | — | Full URL of the SharePoint site. Required to establish the browser session. |
| `include_content` | `bool` | No | `True` | If true, include file content as base64. |
| `headless` | `bool` | No | `True` | Launch in headless mode. |

**Source:** `contelligence-agent/app/tools/sharepoint/browser_download_file.py`

---

## Tool Architecture

All tools follow the same pattern:

1. **Pydantic parameters model** — Every tool defines a `BaseModel` subclass that validates input parameters with types, defaults, and descriptions.
2. **`@define_tool` decorator** — Registers the tool with a name, description, and parameters model in the central tool registry.
3. **Async execution** — Every tool function is `async` and receives the validated parameters and a context dict containing service connectors.
4. **Structured output** — Tools return a `dict` with consistent keys for the agent to process.

Tools are aggregated in `contelligence-agent/app/tools/__init__.py` and bulk-registered at startup via `register_all_tools()`.

### Extending with MCP Servers

In addition to the built-in tools above, the agent can use tools provided by any [MCP-compatible server](https://modelcontextprotocol.io/docs/servers). MCP servers are configured via the **MCP Servers** page in Cowork or via `~/.contelligence/mcp-config.json`. The agent automatically discovers MCP tools and selects them when relevant to an instruction.
