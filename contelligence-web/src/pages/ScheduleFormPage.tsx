import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import { toast } from "sonner";
import { scheduleApi } from "@/lib/api";
import { TriggerTypeSelector } from "@/components/schedules/TriggerTypeSelector";
import type { CreateScheduleRequest, TriggerConfig, InstructOptions } from "@/types";

const DEFAULT_TRIGGER: TriggerConfig = { type: "cron", cron: "0 6 * * 1-5", timezone: "UTC" };
const DEFAULT_OPTIONS: InstructOptions = { model: "gpt-4.1", require_approval: false, persist_outputs: true };

const ScheduleFormPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEdit = !!id;

  const { data: existing } = useQuery({
    queryKey: ["schedule", id],
    queryFn: () => scheduleApi.get(id!),
    enabled: isEdit,
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instruction, setInstruction] = useState("");
  const [trigger, setTrigger] = useState<TriggerConfig>(DEFAULT_TRIGGER);
  const [options, setOptions] = useState<InstructOptions>(DEFAULT_OPTIONS);
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (existing) {
      setName(existing.name);
      setDescription(existing.description || "");
      setInstruction(existing.instruction);
      setTrigger(existing.trigger);
      setOptions(existing.options);
      setTags(existing.tags);
      setEnabled(existing.status === "active");
    }
  }, [existing]);

  const mutation = useMutation({
    mutationFn: (data: CreateScheduleRequest) =>
      isEdit ? scheduleApi.update(id!, data) : scheduleApi.create(data),
    onSuccess: () => {
      toast.success(isEdit ? "Schedule updated" : "Schedule created");
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      navigate("/schedules");
    },
    onError: (err) => toast.error(err.message || "Failed to save schedule"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      name,
      description: description || undefined,
      instruction,
      trigger,
      options,
      tags,
      enabled,
    });
  };

  const addTag = () => {
    const tag = tagInput.trim();
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag]);
      setTagInput("");
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">
        {isEdit ? "Edit Schedule" : "New Schedule"}
      </h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Name & Description */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Basic Info</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-muted-foreground">Name *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Daily Invoice Processing"
                required
                className="bg-secondary border-border text-foreground"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground">Description</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description..."
                className="bg-secondary border-border text-foreground"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground">Instruction *</Label>
              <Textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Extract all invoices from the vendor-inbox container..."
                rows={4}
                required
                className="bg-secondary border-border text-foreground resize-none"
              />
            </div>
          </CardContent>
        </Card>

        {/* Trigger */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Trigger</CardTitle></CardHeader>
          <CardContent>
            <TriggerTypeSelector value={trigger} onChange={setTrigger} />
          </CardContent>
        </Card>

        {/* Options */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Options</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-muted-foreground">Model</Label>
              <Select
                value={options.model ?? "gpt-4.1"}
                onValueChange={(v) => setOptions({ ...options, model: v })}
              >
                <SelectTrigger className="bg-secondary border-border text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gpt-4.1">gpt-4.1</SelectItem>
                  <SelectItem value="gpt-4.1-mini">gpt-4.1-mini</SelectItem>
                  <SelectItem value="gpt-4.1-nano">gpt-4.1-nano</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-muted-foreground">Require Approval</Label>
              <Switch
                checked={options.require_approval ?? false}
                onCheckedChange={(v) => setOptions({ ...options, require_approval: v })}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-muted-foreground">Persist Outputs</Label>
              <Switch
                checked={options.persist_outputs ?? true}
                onCheckedChange={(v) => setOptions({ ...options, persist_outputs: v })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground">Timeout (minutes)</Label>
              <Input
                type="number"
                value={options.timeout_minutes?.toString() ?? "60"}
                onChange={(e) => setOptions({ ...options, timeout_minutes: parseInt(e.target.value) || undefined })}
                className="bg-secondary border-border text-foreground w-32"
              />
            </div>
          </CardContent>
        </Card>

        {/* Tags */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Tags</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                placeholder="Add tag..."
                className="bg-secondary border-border text-foreground"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
              />
              <Button type="button" variant="outline" className="border-border shrink-0" onClick={addTag}>
                Add
              </Button>
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="gap-1 bg-secondary text-muted-foreground">
                    {tag}
                    <button
                      type="button"
                      onClick={() => setTags(tags.filter((t) => t !== tag))}
                      className="ml-1 hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Enabled toggle */}
        <div className="flex items-center justify-between p-4 bg-card rounded-lg border border-border">
          <div>
            <p className="text-sm font-medium text-foreground">Enable Schedule</p>
            <p className="text-xs text-muted-foreground">Schedule will start running immediately when enabled</p>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>

        {/* Submit */}
        <div className="flex gap-3">
          <Button
            type="button"
            variant="outline"
            className="border-border text-muted-foreground"
            onClick={() => navigate("/schedules")}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={mutation.isPending}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {mutation.isPending ? "Saving..." : isEdit ? "Save Changes" : "Create Schedule"}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default ScheduleFormPage;
