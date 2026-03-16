import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft,
  Plus,
  X,
  Play,
  CheckCircle,
  Maximize2,
  Save,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import { agentsApi, skillsApi } from "@/lib/api";
import type {
  AgentDefinitionRecord,
  CreateAgentRequest,
  UpdateAgentRequest,
  ToolInfo,
  McpServerInfo,
  SkillSummary,
  AgentStatusType,
} from "@/types";

interface AgentFormData {
  id: string;
  display_name: string;
  description: string;
  icon: string;
  tags: string[];
  prompt: string;
  tools: string[];
  mcp_servers: string[];
  bound_skills: string[];
  model: string;
  max_tool_calls: number;
  timeout_seconds: number;
  status: AgentStatusType;
}

const iconOptions = [
  { value: "file-text", label: "📄 file-text" },
  { value: "bar-chart", label: "📊 bar-chart" },
  { value: "wrench", label: "🔧 wrench" },
  { value: "scroll", label: "📜 scroll" },
  { value: "shield", label: "🛡️ shield" },
  { value: "receipt", label: "🧾 receipt" },
  { value: "brain", label: "🧠 brain" },
  { value: "search", label: "🔍 search" },
];

const defaultForm: AgentFormData = {
  id: "",
  display_name: "",
  description: "",
  icon: "file-text",
  tags: [],
  prompt: "",
  tools: [],
  mcp_servers: [],
  bound_skills: [],
  model: "gpt-4.1",
  max_tool_calls: 50,
  timeout_seconds: 300,
  status: "draft",
};

function formFromRecord(record: AgentDefinitionRecord): AgentFormData {
  return {
    id: record.id,
    display_name: record.display_name,
    description: record.description,
    icon: record.icon || "file-text",
    tags: record.tags,
    prompt: record.prompt,
    tools: record.tools,
    mcp_servers: record.mcp_servers,
    bound_skills: record.bound_skills,
    model: record.model_override || "gpt-4.1",
    max_tool_calls: record.max_tool_calls,
    timeout_seconds: record.timeout_seconds,
    status: record.status,
  };
}

export default function AgentEditorPage() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = !!agentId && agentId !== "new";

  const [form, setForm] = useState<AgentFormData>(defaultForm);
  const [tagInput, setTagInput] = useState("");
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [testInstruction, setTestInstruction] = useState("");
  const [dirty, setDirty] = useState(false);

  // ── Fetch existing agent for editing ──
  const { data: existingAgent, isLoading: isLoadingAgent } = useQuery({
    queryKey: ["agent", agentId],
    queryFn: () => agentsApi.get(agentId!),
    enabled: isEditing,
  });

  // ── Fetch available tools ──
  const { data: availableTools = [] } = useQuery({
    queryKey: ["agent-tools"],
    queryFn: () => agentsApi.tools(),
  });

  // ── Fetch available MCP servers ──
  const { data: mcpServers = [] } = useQuery({
    queryKey: ["agent-mcp-servers"],
    queryFn: () => agentsApi.mcpServers(),
  });

  // ── Fetch available skills ──
  const { data: availableSkills = [] } = useQuery({
    queryKey: ["skills-list"],
    queryFn: () => skillsApi.list({ status: "active" }),
  });

  // Populate form when existing agent loads
  useEffect(() => {
    if (existingAgent) {
      setForm(formFromRecord(existingAgent));
      setDirty(false);
    }
  }, [existingAgent]);

  const updateField = useCallback(
    <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => {
      setForm((f) => ({ ...f, [key]: value }));
      setDirty(true);
    },
    [],
  );

  // ── Create Mutation ──
  const createMutation = useMutation({
    mutationFn: (data: CreateAgentRequest) => agentsApi.create(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast.success(`Agent "${result.display_name}" created`);
      navigate(`/agents/${result.id}`, { replace: true });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Update Mutation ──
  const updateMutation = useMutation({
    mutationFn: (data: UpdateAgentRequest) => agentsApi.update(agentId!, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["agent", agentId] });
      toast.success(`Agent "${result.display_name}" updated`);
      setDirty(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Test Mutation ──
  const testMutation = useMutation({
    mutationFn: () => agentsApi.test(agentId!, { instruction: testInstruction }),
    onError: (err: Error) => toast.error(err.message),
  });

  const handleSave = (status?: AgentStatusType) => {
    const saveStatus = status ?? form.status;

    if (!form.id.trim()) {
      toast.error("Agent ID is required");
      return;
    }
    if (!form.display_name.trim()) {
      toast.error("Display name is required");
      return;
    }
    if (!form.prompt.trim()) {
      toast.error("System prompt is required");
      return;
    }
    if (form.tools.length === 0) {
      toast.error("Select at least one tool");
      return;
    }

    if (isEditing) {
      updateMutation.mutate({
        display_name: form.display_name,
        description: form.description,
        icon: form.icon,
        prompt: form.prompt,
        tools: form.tools,
        mcp_servers: form.mcp_servers,
        bound_skills: form.bound_skills,
        model: form.model || null,
        max_tool_calls: form.max_tool_calls,
        timeout_seconds: form.timeout_seconds,
        tags: form.tags,
        status: saveStatus,
      });
    } else {
      createMutation.mutate({
        id: form.id,
        display_name: form.display_name,
        description: form.description,
        icon: form.icon,
        prompt: form.prompt,
        tools: form.tools,
        mcp_servers: form.mcp_servers,
        bound_skills: form.bound_skills,
        model: form.model || null,
        max_tool_calls: form.max_tool_calls,
        timeout_seconds: form.timeout_seconds,
        tags: form.tags,
        status: saveStatus,
      });
    }
  };

  const toggleTool = (tool: string) => {
    updateField(
      "tools",
      form.tools.includes(tool)
        ? form.tools.filter((t) => t !== tool)
        : [...form.tools, tool],
    );
  };

  const toggleMcp = (id: string) => {
    updateField(
      "mcp_servers",
      form.mcp_servers.includes(id)
        ? form.mcp_servers.filter((s) => s !== id)
        : [...form.mcp_servers, id],
    );
  };

  const toggleSkill = (skillId: string) => {
    updateField(
      "bound_skills",
      form.bound_skills.includes(skillId)
        ? form.bound_skills.filter((s) => s !== skillId)
        : [...form.bound_skills, skillId],
    );
  };

  const addTag = () => {
    const t = tagInput.trim().toLowerCase();
    if (t && !form.tags.includes(t)) {
      updateField("tags", [...form.tags, t]);
      setTagInput("");
    }
  };

  const removeTag = (tag: string) => {
    updateField(
      "tags",
      form.tags.filter((t) => t !== tag),
    );
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isReadOnly = isEditing && existingAgent?.source === "built-in";

  // Group tools by category
  const toolsByCategory = availableTools.reduce<Record<string, ToolInfo[]>>(
    (acc, tool) => {
      const cat = tool.category || "Other";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(tool);
      return acc;
    },
    {},
  );

  if (isEditing && isLoadingAgent) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 py-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-background border-b border-border px-0 py-4 -mx-6 mb-6">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={() => navigate("/agents")}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground">Back to Agents</span>
        </div>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold font-display tracking-wide text-foreground">
            {isEditing ? `Edit Agent` : "Create New Agent"}
          </h1>
          <div className="flex items-center gap-2">
            {dirty && (
              <span className="text-xs text-muted-foreground">Unsaved changes</span>
            )}
            {!isReadOnly && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSave("draft")}
                  disabled={isSaving}
                >
                  Save Draft
                </Button>
                <Button
                  size="sm"
                  onClick={() => handleSave("active")}
                  disabled={isSaving}
                >
                  <Save className="h-3.5 w-3.5 mr-1" />
                  {isSaving ? "Saving..." : "Save & Activate"}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-6 pb-8">
        {isReadOnly && (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-3 text-sm text-muted-foreground">
            <AlertCircle className="h-4 w-4 shrink-0" />
            This is a built-in agent and cannot be edited. Clone it to create a
            customizable copy.
          </div>
        )}

        {/* IDENTITY */}
        <Section title="IDENTITY">
          <div className="grid gap-4">
            <Field label="ID (slug)">
              <Input
                value={form.id}
                onChange={(e) => updateField("id", e.target.value)}
                placeholder="invoice-expert"
                className="font-mono"
                disabled={isEditing}
              />
              {!isEditing && (
                <p className="text-xs text-muted-foreground mt-1">
                  Lowercase, hyphens only. Cannot be changed after creation.
                </p>
              )}
            </Field>
            <Field label="Display Name">
              <Input
                value={form.display_name}
                onChange={(e) => updateField("display_name", e.target.value)}
                placeholder="Invoice Processing Expert"
                disabled={isReadOnly}
              />
            </Field>
            <Field label="Description">
              <Input
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
                placeholder="Specialized in multi-format invoice extraction & validation"
                disabled={isReadOnly}
              />
            </Field>
            <Field label="Icon">
              <Select
                value={form.icon}
                onValueChange={(v) => updateField("icon", v)}
                disabled={isReadOnly}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {iconOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Tags">
              <div className="flex flex-wrap items-center gap-2">
                {form.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="gap-1">
                    {tag}
                    {!isReadOnly && (
                      <button onClick={() => removeTag(tag)}>
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </Badge>
                ))}
                {!isReadOnly && (
                  <div className="flex gap-1">
                    <Input
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) =>
                        e.key === "Enter" && (e.preventDefault(), addTag())
                      }
                      placeholder="Add tag..."
                      className="h-7 w-28 text-xs"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={addTag}
                    >
                      <Plus className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            </Field>
          </div>
        </Section>

        {/* SYSTEM PROMPT */}
        <Section title="SYSTEM PROMPT">
          <Textarea
            value={form.prompt}
            onChange={(e) => updateField("prompt", e.target.value)}
            placeholder="You are an expert..."
            rows={promptExpanded ? 16 : 6}
            className="font-mono text-xs"
            disabled={isReadOnly}
          />
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-muted-foreground">
              Use Markdown formatting. Reference tool names exactly as shown below.
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs gap-1"
              onClick={() => setPromptExpanded(!promptExpanded)}
            >
              <Maximize2 className="h-3 w-3" />{" "}
              {promptExpanded ? "Collapse" : "Expand"}
            </Button>
          </div>
        </Section>

        {/* TOOLS */}
        <Section title="TOOLS">
          <p className="text-sm text-muted-foreground mb-4">
            Select the atomic tools this agent is allowed to use:
          </p>
          {Object.keys(toolsByCategory).length === 0 ? (
            <p className="text-sm text-muted-foreground italic">
              No tools available. The backend may still be loading.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-x-8 gap-y-1">
              {Object.entries(toolsByCategory).map(([category, tools]) => (
                <div key={category} className="mb-4">
                  <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
                    {category}
                  </p>
                  <div className="space-y-2">
                    {tools.map((tool) => (
                      <label
                        key={tool.name}
                        className="flex items-start gap-2 cursor-pointer group"
                        title={tool.description}
                      >
                        <Checkbox
                          checked={form.tools.includes(tool.name)}
                          onCheckedChange={() => toggleTool(tool.name)}
                          disabled={isReadOnly}
                          className="mt-0.5"
                        />
                        <div>
                          <span className="text-sm font-mono text-foreground group-hover:text-primary transition-colors">
                            {tool.name}
                          </span>
                          {tool.description && (
                            <p className="text-xs text-muted-foreground leading-tight">
                              {tool.description}
                            </p>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* MCP SERVERS */}
        <Section title="MCP SERVERS">
          {mcpServers.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">
              No MCP servers configured.
            </p>
          ) : (
            <div className="space-y-3">
              {mcpServers.map((server: McpServerInfo) => (
                <label
                  key={server.id}
                  className="flex items-center gap-3 cursor-pointer group"
                >
                  <Checkbox
                    checked={form.mcp_servers.includes(server.id)}
                    onCheckedChange={() => toggleMcp(server.id)}
                    disabled={isReadOnly}
                  />
                  <div>
                    <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                      {server.name}
                    </span>
                    <span className="text-xs text-muted-foreground ml-2">
                      — {server.description}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          )}
        </Section>

        {/* BOUND SKILLS */}
        <Section title="BOUND SKILLS">
          <p className="text-sm text-muted-foreground mb-4">
            Select skills whose instructions are always pre-loaded when this agent handles a task:
          </p>
          {availableSkills.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">
              No active skills available. Create skills in the Skills Library.
            </p>
          ) : (
            <div className="space-y-3">
              {availableSkills.map((skill: SkillSummary) => (
                <label
                  key={skill.id}
                  className="flex items-start gap-3 cursor-pointer group"
                >
                  <Checkbox
                    checked={form.bound_skills.includes(skill.name)}
                    onCheckedChange={() => toggleSkill(skill.name)}
                    disabled={isReadOnly}
                    className="mt-0.5"
                  />
                  <div>
                    <span className="text-sm font-mono font-medium text-foreground group-hover:text-primary transition-colors">
                      {skill.name}
                    </span>
                    <p className="text-xs text-muted-foreground leading-tight">
                      {skill.description}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          )}
        </Section>

        {/* ADVANCED SETTINGS */}
        <Section title="ADVANCED SETTINGS">
          <div className="grid gap-4">
            <Field label="Model">
              <Select
                value={form.model}
                onValueChange={(v) => updateField("model", v)}
                disabled={isReadOnly}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gpt-4.1">gpt-4.1</SelectItem>
                  <SelectItem value="gpt-4.1-mini">gpt-4.1-mini</SelectItem>
                  <SelectItem value="gpt-4.1-nano">gpt-4.1-nano</SelectItem>
                  <SelectItem value="o4-mini">o4-mini</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Max Tool Calls">
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={form.max_tool_calls}
                  onChange={(e) =>
                    updateField("max_tool_calls", Number(e.target.value))
                  }
                  className="w-24"
                  disabled={isReadOnly}
                />
                <span className="text-xs text-muted-foreground">
                  (safety limit per delegation)
                </span>
              </div>
            </Field>
            <Field label="Timeout (seconds)">
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={form.timeout_seconds}
                  onChange={(e) =>
                    updateField("timeout_seconds", Number(e.target.value))
                  }
                  className="w-24"
                  disabled={isReadOnly}
                />
                <span className="text-xs text-muted-foreground">
                  (max wall-clock time)
                </span>
              </div>
            </Field>
          </div>
        </Section>

        {/* TEST — only for saved agents */}
        {isEditing && (
          <Section title="TEST">
            <p className="text-sm text-muted-foreground mb-3">
              Send a test instruction to verify this agent works (dry-run):
            </p>
            <div className="flex gap-2">
              <Input
                value={testInstruction}
                onChange={(e) => setTestInstruction(e.target.value)}
                placeholder="Type a test instruction..."
                className="flex-1"
              />
              <Button
                onClick={() => testMutation.mutate()}
                disabled={!testInstruction.trim() || testMutation.isPending}
                className="gap-1 shrink-0"
              >
                <Play className="h-3.5 w-3.5" />{" "}
                {testMutation.isPending ? "Running..." : "Run"}
              </Button>
            </div>
            {testMutation.data && (
              <div className="mt-3 rounded-lg border border-border bg-muted/50 p-4 space-y-2 text-sm">
                <p className="font-medium text-foreground flex items-center gap-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-success" /> Test
                  Result
                </p>
                <p className="text-muted-foreground">
                  Tools available: {testMutation.data.tool_count}
                </p>
                <p className="text-muted-foreground">
                  Estimated tokens: {testMutation.data.estimated_tokens}
                </p>
                {testMutation.data.warnings.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm text-amber-500 font-medium">Warnings:</p>
                    <ul className="list-disc list-inside text-xs text-muted-foreground">
                      {testMutation.data.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <details className="mt-2">
                  <summary className="text-xs text-muted-foreground cursor-pointer">
                    System prompt preview
                  </summary>
                  <pre className="mt-1 text-xs font-mono bg-background rounded p-2 overflow-auto max-h-48 whitespace-pre-wrap">
                    {testMutation.data.system_prompt_preview}
                  </pre>
                </details>
              </div>
            )}
            {testMutation.isError && (
              <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                <AlertCircle className="h-3.5 w-3.5 inline mr-1" />
                {testMutation.error?.message || "Test failed"}
              </div>
            )}
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-4 font-display">
        {title}
      </h3>
      {children}
    </Card>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-3">
      <label className="text-sm text-muted-foreground pt-2">{label}</label>
      <div>{children}</div>
    </div>
  );
}
