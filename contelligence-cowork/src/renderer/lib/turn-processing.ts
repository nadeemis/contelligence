import type {
  AgentEventUnion,
  ToolGroup,
  ProcessedTurn,
  TimelineItem,
  UsageInfoEvent,
  AssistantUsageEvent,
  ToolExecutionStartEvent,
  ToolCallStartEvent,
  ToolCallCompleteEvent,
  ToolExecutionCompleteEvent,
} from "@/types/agent-events";

/**
 * Process a flat array of SSE events into a timeline of turns and orphan events.
 *
 * Events between `turn_start` and `turn_end` are grouped into `ProcessedTurn`s.
 * Within each turn:
 *   - `usage_info` / `assistant_usage` → collected into `usageEvents`
 *   - Tool lifecycle events are grouped by `tool_call_id` into `ToolGroup`s
 *   - All other events become standalone items
 *
 * Events outside any turn (e.g. `session_complete`) become orphan items.
 */
export function processEventsIntoTimeline(events: AgentEventUnion[]): TimelineItem[] {
  const timeline: TimelineItem[] = [];
  let currentTurn: ProcessedTurn | null = null;

  // Per-turn tracking for tool grouping
  let toolGroupMap = new Map<string, ToolGroup>();
  // FIFO queue: tool_name → [tool_call_id, ...] — used to match tool_call_start to exec_start
  let execStartQueues = new Map<string, string[]>();
  // FIFO queue: tool_name → [tool_call_id, ...] — used to match tool_call_complete to the right group
  let callCompleteQueues = new Map<string, string[]>();

  function resetTracking() {
    toolGroupMap = new Map();
    execStartQueues = new Map();
    callCompleteQueues = new Map();
  }

  for (const event of events) {
    // ── Turn boundaries ────────────────────────────────────────────
    if (event.type === "turn_start") {
      if (currentTurn) timeline.push({ kind: "turn", turn: currentTurn });

      const e = event as import("@/types/agent-events").TurnStartEvent;
      currentTurn = {
        turnId: e.turn_id,
        interactionId: e.interaction_id,
        usageEvents: [],
        items: [],
      };
      resetTracking();
      continue;
    }

    if (event.type === "turn_end") {
      if (currentTurn) {
        timeline.push({ kind: "turn", turn: currentTurn });
        currentTurn = null;
      }
      continue;
    }

    // ── Outside any turn → orphan ──────────────────────────────────
    if (!currentTurn) {
      timeline.push({ kind: "orphan", event });
      continue;
    }

    // ── Usage metadata ─────────────────────────────────────────────
    if (event.type === "usage_info" || event.type === "assistant_usage") {
      currentTurn.usageEvents.push(event as UsageInfoEvent | AssistantUsageEvent);
      continue;
    }

    // ── Tool event grouping ────────────────────────────────────────
    if (event.type === "tool_execution_start") {
      const e = event as ToolExecutionStartEvent;
      const group: ToolGroup = {
        toolCallId: e.tool_call_id,
        toolName: e.tool_name,
        events: [event],
      };
      toolGroupMap.set(e.tool_call_id, group);

      const q = execStartQueues.get(e.tool_name) ?? [];
      q.push(e.tool_call_id);
      execStartQueues.set(e.tool_name, q);

      // Placeholder position for this group in the turn items
      currentTurn.items.push({ kind: "tool_group", group });
      continue;
    }

    if (event.type === "tool_call_start") {
      const e = event as ToolCallStartEvent;
      const q = execStartQueues.get(e.tool_name);
      if (q && q.length > 0) {
        const callId = q.shift()!;
        const group = toolGroupMap.get(callId);
        if (group) {
          group.events.push(event);
          // Track for tool_call_complete matching
          const cq = callCompleteQueues.get(e.tool_name) ?? [];
          cq.push(callId);
          callCompleteQueues.set(e.tool_name, cq);
          continue;
        }
      }
      // Fallback: standalone
      currentTurn.items.push({ kind: "event", event });
      continue;
    }

    if (event.type === "tool_call_complete") {
      const e = event as ToolCallCompleteEvent;
      const cq = callCompleteQueues.get(e.tool_name);
      if (cq && cq.length > 0) {
        const callId = cq.shift()!;
        const group = toolGroupMap.get(callId);
        if (group) {
          group.events.push(event);
          continue;
        }
      }
      currentTurn.items.push({ kind: "event", event });
      continue;
    }

    if (event.type === "tool_execution_complete") {
      const e = event as ToolExecutionCompleteEvent;
      const group = toolGroupMap.get(e.tool_call_id);
      if (group) {
        group.events.push(event);
        continue;
      }
      currentTurn.items.push({ kind: "event", event });
      continue;
    }

    // ── Everything else → standalone item ──────────────────────────
    currentTurn.items.push({ kind: "event", event });
  }

  // If stream is still open, push the partial turn
  if (currentTurn) {
    timeline.push({ kind: "turn", turn: currentTurn });
  }

  return timeline;
}
