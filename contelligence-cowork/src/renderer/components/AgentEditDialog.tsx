import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
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
} from "lucide-react";

interface AgentFormData {
  slug: string;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  systemPrompt: string;
  tools: string[];
  mcpServers: string[];
  model: string;
  maxToolCalls: number;
  timeout: number;
}

const toolCategories = {
  Extraction: [
    "extract_pdf",
    "extract_docx",
    "extract_xlsx",
    "extract_pptx",
    "call_doc_intelligence",
    "scrape_webpage",
    "transcribe_audio",
  ],
  Storage: ["read_blob", "write_blob", "upload_to_search", "upsert_cosmos"],
  Query: ["query_search_index", "query_cosmos"],
  AI: ["generate_embeddings"],
};

const mcpServers = [
  { id: "azure-mcp", name: "Azure MCP Server", description: "42+ Azure services" },
  { id: "github-mcp", name: "GitHub MCP Server", description: "Repository access" },
];

const iconOptions = [
  { value: "file-text", label: "📄 file-text" },
  { value: "bar-chart", label: "📊 bar-chart" },
  { value: "wrench", label: "🔧 wrench" },
  { value: "scroll", label: "📜 scroll" },
  { value: "shield", label: "🛡️ shield" },
  { value: "receipt", label: "🧾 receipt" },
];

interface AgentEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent?: {
    slug: string;
    name: string;
    description: string;
    tools: string[];
    tags: string[];
  } | null;
}

export function AgentEditDialog({ open, onOpenChange, agent }: AgentEditDialogProps) {
  const isEditing = !!agent;

  const [form, setForm] = useState<AgentFormData>({
    slug: agent?.slug ?? "",
    name: agent?.name ?? "",
    description: agent?.description ?? "",
    icon: "file-text",
    tags: agent?.tags ?? [],
    systemPrompt: agent
      ? `You are an expert ${agent.name.toLowerCase()}. You:\n\n1. Examine files to determine the best extraction approach\n2. Extract key fields and validate results\n3. Output structured JSON for downstream processing`
      : "",
    tools: agent?.tools ?? [],
    mcpServers: ["azure-mcp"],
    model: "gpt-4.1",
    maxToolCalls: 50,
    timeout: 300,
  });

  const [tagInput, setTagInput] = useState("");
  const [testInstruction, setTestInstruction] = useState("");
  const [testResult, setTestResult] = useState<null | { time: string; tools: string; response: string }>(null);
  const [promptExpanded, setPromptExpanded] = useState(false);

  const toggleTool = (tool: string) => {
    setForm((f) => ({
      ...f,
      tools: f.tools.includes(tool) ? f.tools.filter((t) => t !== tool) : [...f.tools, tool],
    }));
  };

  const toggleMcp = (id: string) => {
    setForm((f) => ({
      ...f,
      mcpServers: f.mcpServers.includes(id) ? f.mcpServers.filter((s) => s !== id) : [...f.mcpServers, id],
    }));
  };

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !form.tags.includes(t)) {
      setForm((f) => ({ ...f, tags: [...f.tags, t] }));
      setTagInput("");
    }
  };

  const removeTag = (tag: string) => {
    setForm((f) => ({ ...f, tags: f.tags.filter((t) => t !== tag) }));
  };

  const runTest = () => {
    setTestResult({
      time: "2.3s",
      tools: "extract_pdf (1), read_blob (1)",
      response: "I extracted 3 tables from the document containing invoice data...",
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto p-0 gap-0">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-card border-b border-border px-6 py-4">
          <div className="flex items-center gap-3 mb-3">
            <button onClick={() => onOpenChange(false)} className="text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="text-sm text-muted-foreground">Back to Agents</span>
          </div>
          <div className="flex items-center justify-between">
            <DialogHeader className="p-0 space-y-0">
              <DialogTitle className="text-xl font-display tracking-wide">
                {isEditing ? `Edit Agent` : "Create New Agent"}
              </DialogTitle>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm">Save Draft</Button>
              <Button size="sm">Save</Button>
            </div>
          </div>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* IDENTITY */}
          <Section title="IDENTITY">
            <div className="grid gap-4">
              <Field label="ID (slug)">
                <Input value={form.slug} onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))} placeholder="invoice-expert" className="font-mono" />
              </Field>
              <Field label="Display Name">
                <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Invoice Processing Expert" />
              </Field>
              <Field label="Description">
                <Input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="Specialized in multi-format invoice..." />
              </Field>
              <Field label="Icon">
                <Select value={form.icon} onValueChange={(v) => setForm((f) => ({ ...f, icon: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {iconOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Tags">
                <div className="flex flex-wrap items-center gap-2">
                  {form.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="gap-1">
                      {tag}
                      <button onClick={() => removeTag(tag)}><X className="h-3 w-3" /></button>
                    </Badge>
                  ))}
                  <div className="flex gap-1">
                    <Input
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                      placeholder="Add tag..."
                      className="h-7 w-28 text-xs"
                    />
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={addTag}>
                      <Plus className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </Field>
            </div>
          </Section>

          {/* SYSTEM PROMPT */}
          <Section title="SYSTEM PROMPT">
            <Textarea
              value={form.systemPrompt}
              onChange={(e) => setForm((f) => ({ ...f, systemPrompt: e.target.value }))}
              placeholder="You are an expert..."
              rows={promptExpanded ? 16 : 6}
              className="font-mono text-xs"
            />
            <div className="flex items-center justify-between mt-2">
              <p className="text-xs text-muted-foreground">
                ℹ️ Use Markdown formatting. Reference tool names exactly as shown in the Tools section below.
              </p>
              <Button variant="ghost" size="sm" className="text-xs gap-1" onClick={() => setPromptExpanded(!promptExpanded)}>
                <Maximize2 className="h-3 w-3" /> {promptExpanded ? "Collapse" : "Expand"}
              </Button>
            </div>
          </Section>

          {/* TOOLS */}
          <Section title="TOOLS">
            <p className="text-sm text-muted-foreground mb-4">Select the atomic tools this agent is allowed to use:</p>
            <div className="grid grid-cols-2 gap-x-8 gap-y-1">
              {Object.entries(toolCategories).map(([category, tools]) => (
                <div key={category} className="mb-4">
                  <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">{category}</p>
                  <div className="space-y-2">
                    {tools.map((tool) => (
                      <label key={tool} className="flex items-center gap-2 cursor-pointer group">
                        <Checkbox
                          checked={form.tools.includes(tool)}
                          onCheckedChange={() => toggleTool(tool)}
                        />
                        <span className="text-sm font-mono text-foreground group-hover:text-primary transition-colors">{tool}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {/* MCP SERVERS */}
          <Section title="MCP SERVERS">
            <div className="space-y-3">
              {mcpServers.map((server) => (
                <label key={server.id} className="flex items-center gap-3 cursor-pointer group">
                  <Checkbox
                    checked={form.mcpServers.includes(server.id)}
                    onCheckedChange={() => toggleMcp(server.id)}
                  />
                  <div>
                    <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">{server.name}</span>
                    <span className="text-xs text-muted-foreground ml-2">— {server.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </Section>

          {/* ADVANCED SETTINGS */}
          <Section title="ADVANCED SETTINGS">
            <div className="grid gap-4">
              <Field label="Model">
                <Select value={form.model} onValueChange={(v) => setForm((f) => ({ ...f, model: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
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
                  <Input type="number" value={form.maxToolCalls} onChange={(e) => setForm((f) => ({ ...f, maxToolCalls: +e.target.value }))} className="w-24" />
                  <span className="text-xs text-muted-foreground">(safety limit per delegation)</span>
                </div>
              </Field>
              <Field label="Timeout (seconds)">
                <div className="flex items-center gap-2">
                  <Input type="number" value={form.timeout} onChange={(e) => setForm((f) => ({ ...f, timeout: +e.target.value }))} className="w-24" />
                  <span className="text-xs text-muted-foreground">(max wall-clock time)</span>
                </div>
              </Field>
            </div>
          </Section>

          {/* TEST */}
          <Section title="TEST">
            <p className="text-sm text-muted-foreground mb-3">Send a test instruction to verify this agent works:</p>
            <div className="flex gap-2">
              <Input
                value={testInstruction}
                onChange={(e) => setTestInstruction(e.target.value)}
                placeholder="Type a test instruction..."
                className="flex-1"
              />
              <Button onClick={runTest} className="gap-1 shrink-0">
                <Play className="h-3.5 w-3.5" /> Run
              </Button>
            </div>
            {testResult && (
              <div className="mt-3 rounded-lg border border-border bg-muted/50 p-4 space-y-1 text-sm">
                <p className="font-medium text-foreground">Test Result:</p>
                <p className="flex items-center gap-1.5 text-foreground">
                  <CheckCircle className="h-3.5 w-3.5 text-success" /> Agent responded in {testResult.time}
                </p>
                <p className="text-muted-foreground">Tool calls: {testResult.tools}</p>
                <p className="text-muted-foreground">Response: "{testResult.response}"</p>
              </div>
            )}
          </Section>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-card border-t border-border px-6 py-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="outline">Save as Draft</Button>
          <Button>Activate</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-4 font-display">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-3">
      <label className="text-sm text-muted-foreground pt-2">{label}</label>
      {children}
    </div>
  );
}