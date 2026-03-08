import { useState, useEffect, useRef, useMemo, useCallback, Fragment } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { User, StopCircle, Wrench, Clock, FileText, AlertCircle, Radio, Plus, ArrowDownToLine, PauseCircle, ChevronDown, ChevronUp } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { ChatAgentPicker } from "@/components/ChatAgentPicker";
import { ChatSkillPicker } from "@/components/ChatSkillPicker";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { ToolResultCard } from "@/components/chat/ToolResultCard";
import { TurnBox } from "@/components/chat/TurnBox";
import { ToolCallGroup } from "@/components/chat/ToolCallGroup";
import { ChatInput } from "@/components/chat/ChatInput";
import { useAgentStream } from "@/hooks/useAgentStream";
import { agentApi } from "@/lib/api";
import { processEventsIntoTimeline } from "@/lib/turn-processing";
import { formatDate, formatDuration, statusIcon } from "@/lib/format";
import type { ConversationTurn } from "@/types";
import type { AgentEventUnion } from "@/types/agent-events";

const Chat = () => {
  const { sessionId: urlSessionId } = useParams();
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | null>(urlSessionId ?? null);
  const [userMessages, setUserMessages] = useState<string[]>([]);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const { events, isStreaming, sessionTitle, connect, reset } = useAgentStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const [summaryFullyExpanded, setSummaryFullyExpanded] = useState(false);

  // ── Fetch available models from backend ──
  const { data: availableModels = [] } = useQuery({
    queryKey: ["models"],
    queryFn: () => agentApi.listModels(),
    staleTime: 5 * 60 * 1000,
  });

  // Select first model as default once loaded
  useEffect(() => {
    if (!selectedModel && availableModels.length > 0) {
      setSelectedModel(availableModels[0].id);
    }
  }, [availableModels, selectedModel]);

  // Re-enable auto-scroll when a new streaming session starts
  useEffect(() => {
    if (isStreaming) setAutoScroll(true);
  }, [isStreaming]);

  // ── Load existing session data when navigating to /chat/:sessionId ──
  const { data: session } = useQuery({
    queryKey: ["session", urlSessionId],
    queryFn: () => agentApi.getSession(urlSessionId!),
    enabled: !!urlSessionId,
  });

  const { data: history } = useQuery({
    queryKey: ["session-logs", urlSessionId],
    queryFn: () => agentApi.getSessionLogs(urlSessionId!),
    enabled: !!urlSessionId,
  });

  // Update sessionId if URL changes (e.g. navigating from sessions list)
  useEffect(() => {
    if (urlSessionId && urlSessionId !== sessionId) {
      reset();
      setUserMessages([]);
      setSessionId(urlSessionId);
    }
  }, [urlSessionId, sessionId, reset]);

  // Auto-scroll to bottom on new events (only when toggle is on)
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, userMessages, history, autoScroll]);

  const sendInstruction = useMutation({
    mutationFn: async (instruction: string) => {
      setUserMessages((prev) => [...prev, instruction]);
      const options: { agents?: string[]; skill_ids?: string[]; model?: string } = {};
      if (selectedAgents.length > 0) options.agents = selectedAgents;
      if (selectedSkills.length > 0) options.skill_ids = selectedSkills;
      if (selectedModel) options.model = selectedModel;
      const res = await agentApi.instruct(instruction, sessionId ?? undefined, options);
      setSessionId(res.session_id);
      // Connect to SSE stream after instruct succeeds
      connect(res.session_id);
      // Update URL to include session ID for deep-linking
      if (!urlSessionId) {
        navigate(`/chat/${res.session_id}`, { replace: true });
      }
    },
  });

  const sendReply = useMutation({
    mutationFn: async (message: string) => {
      if (sessionId) {
        setUserMessages((prev) => [...prev, message]);
        await agentApi.reply(sessionId, message);
      }
    },
  });

  const cancelSession = useMutation({
    mutationFn: async () => {
      if (sessionId) await agentApi.cancel(sessionId);
    },
  });

  const handleSend = (msg: string) => {
    if (isStreaming && events.some((e) => e.type === "approval_required")) {
      sendReply.mutate(msg);
    } else {
      sendInstruction.mutate(msg);
    }
  };

  // ── Render prior conversation history (loaded from API) ──
  const renderHistory = () => {
    if (!history || history.length === 0 || isStreaming) return null;

    const items: React.ReactNode[] = [];

    for (const turn of history as ConversationTurn[]) {
      const key = `hist-${turn.sequence}`;

      if (turn.role === "user") {
        if (!turn.prompt) continue;
        items.push(
          <div key={key} className="flex gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
              <User className="h-3.5 w-3.5 text-accent" />
            </div>
            <div className="rounded-lg bg-secondary p-3 max-w-[80%]">
              <p className="text-sm text-foreground">{turn.prompt}</p>
            </div>
          </div>,
        );
      } else if (turn.role === "tool" && turn.tool_call) {
        items.push(
          <ToolResultCard
            key={key}
            callId={turn.tool_call.tool_name}
            toolName={turn.tool_call.tool_name}
            result={turn.tool_call.error ?? turn.tool_call.result ?? ""}
            parameters={turn.tool_call.parameters}
            timestamp={turn.timestamp}
            startedAt={turn.tool_call.started_at}
            completedAt={turn.tool_call.completed_at}
            durationMs={turn.tool_call.duration_ms}
          />,
        );
      } else if (turn.role === "assistant") {
        if (turn.reasoning) {
          items.push(
            <ChatMessage
              key={`${key}-thinking`}
              event={{ type: "thinking", content: turn.reasoning, timestamp: turn.timestamp, payload: {} } as AgentEventUnion}
              onApprove={() => {}}
            />,
          );
        }
        if (turn.content) {
          items.push(
            <ChatMessage
              key={key}
              event={{ type: "message", content: turn.content, timestamp: turn.timestamp, payload: {} } as AgentEventUnion}
              onApprove={() => {}}
            />,
          );
        }
      }
    }

    return items;
  };

  // ── Process events into turn-based timeline ──
  const timeline = useMemo(() => processEventsIntoTimeline(events), [events]);

  // ── Render live timeline (new messages + SSE events) ──
  const renderTimeline = () => {
    const items: React.ReactNode[] = [];
    let userIdx = 0;

    // First user message
    if (userMessages.length > 0) {
      items.push(
        <div key={`user-${userIdx}`} className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
            <User className="h-3.5 w-3.5 text-accent" />
          </div>
          <div className="rounded-lg bg-secondary p-3 max-w-[80%]">
            <p className="text-sm text-foreground">{userMessages[0]}</p>
          </div>
        </div>
      );
      userIdx = 1;
    }

    for (let ti = 0; ti < timeline.length; ti++) {
      const tItem = timeline[ti];

      if (tItem.kind === "turn") {
        const { turn } = tItem;
        items.push(
          <TurnBox key={`turn-${turn.turnId}-${ti}`} turn={turn}>
            {turn.items.map((item, i) => {
              if (item.kind === "tool_group") {
                return <ToolCallGroup key={`tg-${i}`} group={item.group} />;
              }
              return (
                <ChatMessage
                  key={`ev-${i}`}
                  event={item.event}
                  onApprove={(msg) => sendReply.mutate(msg)}
                />
              );
            })}
          </TurnBox>
        );
      } else {
        // Orphan event (e.g. session_complete)
        items.push(
          <ChatMessage
            key={`orphan-${ti}`}
            event={tItem.event}
            onApprove={(msg) => sendReply.mutate(msg)}
          />
        );

        // Insert next user message after a terminal event
        if (
          (tItem.event.type === "done" || tItem.event.type === "error") &&
          userIdx < userMessages.length
        ) {
          items.push(
            <div key={`user-${userIdx}`} className="flex gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
                <User className="h-3.5 w-3.5 text-accent" />
              </div>
              <div className="rounded-lg bg-secondary p-3 max-w-[80%]">
                <p className="text-sm text-foreground">{userMessages[userIdx]}</p>
              </div>
            </div>
          );
          userIdx++;
        }
      }
    }

    return items;
  };

  const isExistingSession = !!urlSessionId && !!session;
  const isSessionFinished = session && session.status !== "active" && session.status !== "waiting_approval";

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Chat</h1>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Model:</span>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              <SelectTrigger className="h-7 w-[180px] text-xs">
                <SelectValue placeholder="Select model…" />
              </SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => {
              reset();
              setSessionId(null);
              setUserMessages([]);
              setSelectedAgents([]);
              setSelectedSkills([]);
              navigate("/chat", { replace: true });
            }}
          >
            <Plus className="h-3 w-3 mr-1" /> New Session
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <Badge variant="outline" className="border-border text-muted-foreground font-mono text-xs">
              Session: {sessionId.slice(0, 8)}...
            </Badge>
          )}
          {isExistingSession && !isStreaming && (
            <Badge variant="outline" className="border-border text-muted-foreground text-xs">
              {statusIcon(session.status)} {session.status}
            </Badge>
          )}
          {isStreaming && (
            <>
              <Badge variant="outline" className="border-primary/50 bg-primary/5 text-primary text-xs gap-1.5 pr-2.5">
                <Radio className="h-3 w-3 animate-pulse-glow" />
                <span>Streaming</span>
                <span className="flex gap-0.5">
                  <span className="h-1 w-1 rounded-full bg-primary animate-bounce [animation-delay:0ms]" />
                  <span className="h-1 w-1 rounded-full bg-primary animate-bounce [animation-delay:150ms]" />
                  <span className="h-1 w-1 rounded-full bg-primary animate-bounce [animation-delay:300ms]" />
                </span>
              </Badge>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs border-destructive text-destructive hover:bg-destructive/10"
                onClick={() => cancelSession.mutate()}
              >
                <StopCircle className="h-3 w-3 mr-1" /> Cancel
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Session title from agent */}
      {sessionTitle && (
        <p className="mb-2 text-sm font-medium text-muted-foreground truncate" title={sessionTitle}>
          {sessionTitle}
        </p>
      )}

      {/* Session summary banner for resumed sessions */}
      {isExistingSession && isSessionFinished && !isStreaming && userMessages.length === 0 && (
        <div className="mb-3 rounded-lg border border-border bg-secondary/50 text-sm">
          <button
            type="button"
            onClick={() => setSummaryExpanded((v) => !v)}
            className="flex w-full items-center justify-between p-3 text-left hover:bg-secondary/80 rounded-lg transition-colors"
          >
            <div className="flex items-center gap-4 text-muted-foreground">
              <span className="flex items-center gap-1"><Wrench className="h-3.5 w-3.5" /> {session.metrics.total_tool_calls} tool calls</span>
              <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> {formatDuration(session.metrics.total_duration_seconds)}</span>
              <span className="flex items-center gap-1"><FileText className="h-3.5 w-3.5" /> {session.metrics.documents_processed} docs</span>
              {session.metrics.errors_encountered > 0 && (
                <span className="flex items-center gap-1 text-destructive"><AlertCircle className="h-3.5 w-3.5" /> {session.metrics.errors_encountered} errors</span>
              )}
            </div>
            {summaryExpanded ? <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />}
          </button>
          {summaryExpanded && session.summary && (
            <div className="px-3 pb-3 text-foreground border-t border-border pt-2">
              <div className={`overflow-hidden ${summaryFullyExpanded ? '' : 'max-h-[15em] line-clamp-[10]'}`}>
                <MarkdownContent>{session.summary}</MarkdownContent>
              </div>
              <button
                type="button"
                onClick={() => setSummaryFullyExpanded((v) => !v)}
                className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {summaryFullyExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {summaryFullyExpanded ? 'Show less' : 'Show more'}
              </button>
            </div>
          )}
        </div>
      )}

      <Card className="flex-1 bg-card border-border overflow-hidden flex flex-col relative">
        {/* Streaming progress bar */}
        {isStreaming && (
          <div className="h-0.5 w-full bg-primary/10 overflow-hidden">
            <div className="h-full w-1/2 bg-primary/60 rounded-full animate-stream-flow" />
          </div>
        )}
        {/* Auto-scroll toggle – visible only while streaming */}
        {isStreaming && (
          <div className="absolute top-2 right-3 z-10">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant={autoScroll ? "default" : "outline"}
                  className="h-7 w-7 p-0"
                  onClick={() => setAutoScroll((v) => !v)}
                >
                  {autoScroll ? (
                    <ArrowDownToLine className="h-3.5 w-3.5" />
                  ) : (
                    <PauseCircle className="h-3.5 w-3.5" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">
                {autoScroll ? "Auto-scroll ON – click to pause" : "Auto-scroll OFF – click to resume"}
              </TooltipContent>
            </Tooltip>
          </div>
        )}
        <CardContent ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-4">
          {!isExistingSession && events.length === 0 && userMessages.length === 0 && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Send an instruction to start a new session
            </div>
          )}

          {/* Existing session history */}
          {renderHistory()}

          {/* Separator between history and new messages */}
          {history && history.length > 0 && userMessages.length > 0 && (
            <div className="flex items-center gap-2 py-2">
              <div className="flex-1 border-t border-border" />
              <span className="text-xs text-muted-foreground">New messages</span>
              <div className="flex-1 border-t border-border" />
            </div>
          )}

          {/* Live timeline */}
          {renderTimeline()}

          {(sendInstruction.isPending || sendReply.isPending) && !isStreaming && (
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
              Sending...
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mt-4 space-y-3">
        <ChatAgentPicker
          selected={selectedAgents}
          onSelectionChange={setSelectedAgents}
        />
        <ChatSkillPicker
          selected={selectedSkills}
          onSelectionChange={setSelectedSkills}
        />
        <ChatInput
          onSend={handleSend}
          disabled={sendInstruction.isPending || sendReply.isPending}
          placeholder={
            isStreaming
              ? "Reply to agent..."
              : isSessionFinished
                ? "Send a follow-up instruction to resume this session..."
                : "Type your instruction..."
          }
        />
      </div>
    </div>
  );
};

export default Chat;