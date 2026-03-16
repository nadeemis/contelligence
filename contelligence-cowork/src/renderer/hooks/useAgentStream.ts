import { useState, useCallback, useRef } from "react";
import type { AgentEventUnion, ThinkingEvent, MessageEvent as AgentMessageEvent } from "@/types/agent-events";
import { getBaseUrlSync } from "@/lib/api";

/**
 * Map a backend named SSE event into the frontend AgentEventUnion shape.
 * Returns `null` for events that should be silently ignored (keepalive).
 */
function mapBackendEvent(eventType: string, raw: Record<string, unknown>): AgentEventUnion | null {
  const ts = new Date().toISOString();
  const payload = { ...raw };

  switch (eventType) {
    // ── Turn lifecycle ────────────────────────────────────────────────
    case "turn_start":
      return { type: "turn_start", turn_id: String(raw.turn_id ?? ""), interaction_id: String(raw.interaction_id ?? ""), timestamp: ts, payload };

    case "turn_end":
      return { type: "turn_end", turn_id: String(raw.turn_id ?? ""), timestamp: ts, payload };

    // ── Usage / cost ──────────────────────────────────────────────────
    case "usage_info":
      return {
        type: "usage_info",
        current_tokens: Number(raw.current_tokens ?? 0),
        token_limit: Number(raw.token_limit ?? 0),
        messages_length: Number(raw.messages_length ?? 0),
        timestamp: ts,
        payload,
      };

    case "assistant_usage":
      return {
        type: "assistant_usage",
        input_tokens: Number(raw.input_tokens ?? 0),
        output_tokens: Number(raw.output_tokens ?? 0),
        cache_read_tokens: Number(raw.cache_read_tokens ?? 0),
        cache_write_tokens: Number(raw.cache_write_tokens ?? 0),
        model: String(raw.model ?? ""),
        duration: Number(raw.duration ?? 0),
        cost: Number(raw.cost ?? 0),
        timestamp: ts,
        payload,
      };

    // ── Reasoning / content ───────────────────────────────────────────
    case "reasoning":
      return { type: "thinking", content: String(raw.content ?? ""), timestamp: ts, payload };

    case "message":
      return { type: "message", content: String(raw.content ?? ""), timestamp: ts, payload };

    // ── Tool lifecycle ────────────────────────────────────────────────
    case "tool_execution_start":
      return {
        type: "tool_execution_start",
        tool_name: String(raw.tool_name ?? "unknown"),
        tool_call_id: String(raw.tool_call_id ?? ""),
        arguments: (raw.arguments as Record<string, unknown>) ?? {},
        timestamp: ts,
        payload,
      };

    case "tool_call_start":
      return {
        type: "tool_call_start",
        tool_name: String(raw.tool ?? "unknown"),
        params: String(raw.params ?? "{}"),
        timestamp: ts,
        payload,
      };

    case "tool_call_complete":
      return {
        type: "tool_call_complete",
        tool_name: String(raw.tool ?? "unknown"),
        duration_ms: Number(raw.duration_ms ?? 0),
        timestamp: ts,
        payload,
      };

    case "tool_execution_complete":
      return {
        type: "tool_execution_complete",
        tool_call_id: String(raw.tool_call_id ?? ""),
        result: raw.result ?? {},
        duration: raw.duration != null ? Number(raw.duration) : null,
        timestamp: ts,
        payload,
      };

    case "tool_call_error":
      return { type: "error", message: `Tool ${raw.tool}: ${raw.error}`, recoverable: true, timestamp: ts, payload };

    // ── Sub-agent delegation ──────────────────────────────────────────
    case "subagent_started":
      return { type: "subagent_started", agent_name: String(raw.agent_name ?? ""), timestamp: ts, payload };

    case "subagent_completed":
      return { type: "subagent_completed", agent_name: String(raw.agent_name ?? ""), summary: raw.summary != null ? String(raw.summary) : null, timestamp: ts, payload };

    case "delegation_start":
    case "delegation_progress":
      return { type: "thinking", content: String(raw.message ?? raw.content ?? `Delegating to ${raw.agent ?? "sub-agent"}…`), timestamp: ts, payload };

    case "delegation_complete":
      return { type: "message", content: String(raw.result ?? raw.content ?? "Delegation complete"), timestamp: ts, payload };

    case "delegation_error":
      return { type: "error", message: `Delegation failed: ${raw.error ?? "unknown"}`, recoverable: true, timestamp: ts, payload };

    // ── Approval ──────────────────────────────────────────────────────
    case "approval_required":
      return {
        type: "approval_required",
        tool_name: String(raw.tool_name ?? "unknown"),
        arguments: (raw.arguments as Record<string, unknown>) ?? {},
        reason: String(raw.reason ?? ""),
        timestamp: ts,
        payload,
      };

    // ── Terminal ──────────────────────────────────────────────────────
    case "session_complete":
      return { type: "done", session_id: String(raw.session_id ?? ""), summary: "", timestamp: ts, payload };

    case "session_shutdown":
      return { type: "done", session_id: String(raw.session_id ?? ""), summary: "", timestamp: ts, payload };

    case "session_error":
      return { type: "error", message: String(raw.error ?? "Unknown error"), recoverable: false, timestamp: ts, payload };

    case "session_title_changed":
      return { type: "session_title_changed", title: String(raw.title ?? ""), timestamp: ts, payload };

    // ── Silently ignored ──────────────────────────────────────────────
    case "keepalive":
    case "user_message":
      return null;

    default:
      console.debug("[SSE] Unhandled event type:", eventType, raw);
      return null;
  }
}

/** All backend event types the hook should listen for. */
const BACKEND_EVENT_TYPES = [
  "reasoning",
  "message",
  "tool_execution_start",
  "tool_call_start",
  "tool_call_complete",
  "tool_execution_complete",
  "tool_call_error",
  "approval_required",
  "session_start",
  "session_complete",
  "session_shutdown",
  "session_error",
  "delegation_start",
  "delegation_progress",
  "delegation_complete",
  "delegation_error",
  "session_title_changed",
  "turn_start",
  "turn_end",
  "usage_info",
  "assistant_usage",
  "subagent_started",
  "subagent_completed",
  "keepalive",
  "user_message",
] as const;

/** Terminal event types that indicate the stream is finished. */
const TERMINAL_TYPES = new Set(["session_complete", "session_error"]);

/** Event types whose content should be merged (appended) when arriving consecutively. */
const STREAMABLE_TYPES = new Set<AgentEventUnion["type"]>(["thinking", "message"]);

/**
 * SSE streaming hook — does NOT auto-connect.
 * Call `connect(sessionId)` after the instruct endpoint responds
 * to start listening for events.
 *
 * The backend sends **named** SSE events (`event: reasoning`, etc.)
 * so we register `addEventListener` for each known type instead of
 * relying on the generic `onmessage` handler.
 */
export function useAgentStream() {
  const [events, setEvents] = useState<AgentEventUnion[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback((sessionId: string) => {
    // Close any existing connection first
    eventSourceRef.current?.close();

    const url = `${getBaseUrlSync()}/agent/sessions/${sessionId}/stream`;
    const es = new EventSource(url);
    eventSourceRef.current = es;
    setIsStreaming(true);

    // Register a named-event listener for every backend event type
    for (const eventType of BACKEND_EVENT_TYPES) {
      es.addEventListener(eventType, (evt: MessageEvent) => {
        try {
          const raw = JSON.parse(evt.data);
          const mapped = mapBackendEvent(eventType, raw);
          if (mapped) {
            // Session title changes update dedicated state, not the event list
            if (mapped.type === "session_title_changed") {
              setSessionTitle((mapped as import("@/types/agent-events").SessionTitleChangedEvent).title);
            } else {
              setEvents((prev) => {
                // Merge consecutive streamable events (thinking/message) into one entry
                if (
                  STREAMABLE_TYPES.has(mapped.type) &&
                  prev.length > 0 &&
                  prev[prev.length - 1].type === mapped.type
                ) {
                  const last = prev[prev.length - 1] as ThinkingEvent | AgentMessageEvent;
                  const incoming = mapped as ThinkingEvent | AgentMessageEvent;
                  return [
                    ...prev.slice(0, -1),
                    { ...last, content: last.content + incoming.content },
                  ];
                }
                return [...prev, mapped];
              });
            }
          }
        } catch (e) {
          console.error(`[SSE] Failed to parse '${eventType}' event:`, e);
        }

        if (TERMINAL_TYPES.has(eventType)) {
          es.close();
          setIsStreaming(false);
        }
      });
    }

    // Fallback: catch any unnamed events just in case
    es.onmessage = (evt) => {
      try {
        const raw = JSON.parse(evt.data);
        const type = raw.type ?? "unknown";
        const mapped = mapBackendEvent(type, raw);
        if (mapped) {
          setEvents((prev) => {
            if (
              STREAMABLE_TYPES.has(mapped.type) &&
              prev.length > 0 &&
              prev[prev.length - 1].type === mapped.type
            ) {
              const last = prev[prev.length - 1] as ThinkingEvent | AgentMessageEvent;
              const incoming = mapped as ThinkingEvent | AgentMessageEvent;
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + incoming.content },
              ];
            }
            return [...prev, mapped];
          });
        }
      } catch {
        // ignore parse failures on unnamed events
      }
    };

    es.onerror = () => {
      es.close();
      setIsStreaming(false);
    };
  }, []);

  const reset = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setEvents([]);
    setIsStreaming(false);
    setSessionTitle(null);
  }, []);

  return { events, isStreaming, sessionTitle, connect, reset };
}
