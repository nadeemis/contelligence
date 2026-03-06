import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
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
  Save,
  AlertCircle,
  CheckCircle,
  ShieldCheck,
  Upload,
  FileText,
  Trash2,
  Archive,
} from "lucide-react";
import { toast } from "sonner";
import { skillsApi } from "@/lib/api";
import type {
  SkillRecord,
  CreateSkillRequest,
  UpdateSkillRequest,
  SkillValidationResult,
  SkillStatusType,
} from "@/types";

interface SkillFormData {
  name: string;
  description: string;
  version: string;
  license: string;
  tags: string[];
  compatibility: string;
  instructions: string;
  status: SkillStatusType;
}

const defaultForm: SkillFormData = {
  name: "",
  description: "",
  version: "1.0.0",
  license: "MIT",
  tags: [],
  compatibility: "",
  instructions: "",
  status: "draft",
};

function formFromRecord(record: SkillRecord): SkillFormData {
  return {
    name: record.name,
    description: record.description,
    version: record.metadata?.version || "1.0.0",
    license: record.license || "MIT",
    tags: record.tags,
    compatibility: record.compatibility || "",
    instructions: record.instructions || "",
    status: record.status,
  };
}

export default function SkillEditorPage() {
  const { skillId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = !!skillId && skillId !== "new";

  const [form, setForm] = useState<SkillFormData>(defaultForm);
  const [tagInput, setTagInput] = useState("");
  const [dirty, setDirty] = useState(false);
  const [validation, setValidation] = useState<SkillValidationResult | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const zipInputRef = useRef<HTMLInputElement>(null);

  // ── Fetch existing skill for editing ──
  const { data: existingSkill, isLoading: isLoadingSkill } = useQuery({
    queryKey: ["skill", skillId],
    queryFn: () => skillsApi.get(skillId!),
    enabled: isEditing,
  });

  useEffect(() => {
    if (existingSkill) {
      setForm(formFromRecord(existingSkill));
      setDirty(false);
    }
  }, [existingSkill]);

  const updateField = useCallback(
    <K extends keyof SkillFormData>(key: K, value: SkillFormData[K]) => {
      setForm((f) => ({ ...f, [key]: value }));
      setDirty(true);
      setValidation(null); // Clear old validation on change
    },
    [],
  );

  // ── Create Mutation ──
  const createMutation = useMutation({
    mutationFn: (data: CreateSkillRequest) => skillsApi.create(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      toast.success(`Skill "${result.name}" created`);
      navigate(`/skills/${result.id}`, { replace: true });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Update Mutation ──
  const updateMutation = useMutation({
    mutationFn: (data: UpdateSkillRequest) =>
      skillsApi.update(skillId!, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      queryClient.invalidateQueries({ queryKey: ["skill", skillId] });
      toast.success(`Skill "${result.name}" updated`);
      setDirty(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Fetch skill files ──
  const { data: skillFiles = [], refetch: refetchFiles } = useQuery({
    queryKey: ["skill-files", skillId],
    queryFn: () => skillsApi.files(skillId!),
    enabled: isEditing,
  });

  // ── Validate Mutation ──
  const validateMutation = useMutation({
    mutationFn: () => {
      // Build full SKILL.md content for validation
      const content = `---\nname: ${form.name}\ndescription: ${form.description}\nlicense: ${form.license}\n---\n\n${form.instructions}`;
      return skillsApi.validate(content);
    },
    onSuccess: (result) => setValidation(result),
    onError: (err: Error) => toast.error(err.message),
  });

  // ── File Upload Mutation ──
  const uploadFileMutation = useMutation({
    mutationFn: ({ file, path }: { file: File; path: string }) =>
      skillsApi.uploadFile(skillId!, file, path),
    onSuccess: () => {
      refetchFiles();
      queryClient.invalidateQueries({ queryKey: ["skill", skillId] });
      toast.success("File uploaded");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Zip Upload Mutation ──
  const uploadZipMutation = useMutation({
    mutationFn: (file: File) => skillsApi.uploadZip(skillId!, file),
    onSuccess: (result) => {
      refetchFiles();
      queryClient.invalidateQueries({ queryKey: ["skill", skillId] });
      toast.success(`Zip extracted — ${result.files_added} files added`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── File Delete Mutation ──
  const deleteFileMutation = useMutation({
    mutationFn: (path: string) => skillsApi.deleteFile(skillId!, path),
    onSuccess: () => {
      refetchFiles();
      queryClient.invalidateQueries({ queryKey: ["skill", skillId] });
      toast.success("File deleted");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleSave = (status?: SkillStatusType) => {
    const saveStatus = status ?? form.status;
    if (!form.name.trim()) {
      toast.error("Skill name is required");
      return;
    }
    if (!form.instructions.trim()) {
      toast.error("Instruction body is required");
      return;
    }

    const metadata: Record<string, string> = {};
    if (form.version) metadata.version = form.version;

    const payload = {
      name: form.name,
      description: form.description,
      license: form.license,
      tags: form.tags,
      compatibility: form.compatibility || null,
      metadata,
      instructions: form.instructions,
      status: saveStatus,
    };

    if (isEditing) {
      updateMutation.mutate(payload);
    } else {
      createMutation.mutate(payload);
    }
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

  const handleFileUpload = (files: FileList | null) => {
    if (!files || !isEditing) return;
    for (const file of Array.from(files)) {
      // Determine target path based on file extension
      let prefix = "assets/";
      if (file.name.endsWith(".md")) prefix = "references/";
      else if (file.name.endsWith(".py")) prefix = "scripts/";
      uploadFileMutation.mutate({ file, path: `${prefix}${file.name}` });
    }
  };

  const handleZipUpload = (files: FileList | null) => {
    if (!files || !isEditing || files.length === 0) return;
    uploadZipMutation.mutate(files[0]);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isReadOnly = isEditing && existingSkill?.source === "built-in";

  if (isEditing && isLoadingSkill) {
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
            onClick={() => navigate("/skills")}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground">
            Back to Skills Library
          </span>
        </div>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold font-display tracking-wide text-foreground">
            {isEditing ? `Edit Skill` : "Create New Skill"}
          </h1>
          <div className="flex items-center gap-2">
            {dirty && (
              <span className="text-xs text-muted-foreground">
                Unsaved changes
              </span>
            )}
            {!isReadOnly && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => validateMutation.mutate()}
                  disabled={validateMutation.isPending || !form.instructions.trim()}
                >
                  <ShieldCheck className="h-3.5 w-3.5 mr-1" />
                  {validateMutation.isPending ? "Validating..." : "Validate"}
                </Button>
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
            This is a built-in skill and cannot be edited.
          </div>
        )}

        {/* Validation banner */}
        {validation && (
          <div
            className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
              validation.valid
                ? "border-primary/30 bg-primary/5 text-foreground"
                : "border-destructive/30 bg-destructive/5 text-destructive"
            }`}
          >
            {validation.valid ? (
              <CheckCircle className="h-4 w-4 shrink-0 mt-0.5 text-primary" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            )}
            <div>
              <p className="font-medium">
                {validation.valid
                  ? "Skill definition is valid"
                  : "Validation failed"}
              </p>
              {validation.errors && validation.errors.length > 0 && (
                <ul className="mt-1 list-disc list-inside text-xs">
                  {validation.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
              {validation.warnings && validation.warnings.length > 0 && (
                <ul className="mt-1 list-disc list-inside text-xs text-amber-600">
                  {validation.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* METADATA */}
        <Section title="METADATA">
          <div className="grid gap-4">
            <Field label="Name (slug)">
              <Input
                value={form.name}
                onChange={(e) => updateField("name", e.target.value)}
                placeholder="invoice-processing"
                className="font-mono"
                disabled={isReadOnly}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Lowercase with hyphens. Used as the skill identifier.
              </p>
            </Field>
            <Field label="Description">
              <Textarea
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
                placeholder="Describe what this skill teaches agents to do..."
                rows={2}
                disabled={isReadOnly}
              />
            </Field>
            <Field label="Version">
              <Input
                value={form.version}
                onChange={(e) => updateField("version", e.target.value)}
                placeholder="1.0.0"
                className="w-32"
                disabled={isReadOnly}
              />
            </Field>
            <Field label="License">
              <Select
                value={form.license}
                onValueChange={(v) => updateField("license", v)}
                disabled={isReadOnly}
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MIT">MIT</SelectItem>
                  <SelectItem value="Apache-2.0">Apache-2.0</SelectItem>
                  <SelectItem value="BSD-3-Clause">BSD-3-Clause</SelectItem>
                  <SelectItem value="proprietary">Proprietary</SelectItem>
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
            <Field label="Compatibility">
              <Input
                value={form.compatibility}
                onChange={(e) => updateField("compatibility", e.target.value)}
                placeholder="e.g. Contelligence v1.0+, doc-processor"
                disabled={isReadOnly}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Compatibility string (agent slugs, version requirements). Leave
                empty for universal compatibility.
              </p>
            </Field>
          </div>
        </Section>

        {/* INSTRUCTION BODY */}
        <Section title="INSTRUCTION BODY">
          <p className="text-sm text-muted-foreground mb-3">
            Write the skill instructions in Markdown. This content is injected
            into the agent&apos;s system prompt when the skill is active.
          </p>
          <Textarea
            value={form.instructions}
            onChange={(e) => updateField("instructions", e.target.value)}
            placeholder={`# Invoice Processing Skill\n\nWhen processing invoices:\n1. Extract vendor name, date, total amount...\n2. Validate against known schemas...\n3. Flag anomalies...`}
            rows={18}
            className="font-mono text-xs"
            disabled={isReadOnly}
          />
          <p className="text-xs text-muted-foreground mt-2">
            {form.instructions.length} characters &middot;{" "}
            ~{Math.ceil(form.instructions.length / 4)} tokens
          </p>
        </Section>

        {/* SKILL FILES */}
        {isEditing && (
          <Section title="SKILL FILES">
            <p className="text-sm text-muted-foreground mb-3">
              Attach reference documents, scripts, and assets to this skill.
              Files are organized into <code>references/</code>,{" "}
              <code>scripts/</code>, and <code>assets/</code> directories.
            </p>

            {/* File list */}
            {skillFiles.length > 0 ? (
              <div className="space-y-1 mb-4">
                {skillFiles.map((f) => (
                  <div
                    key={f}
                    className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="font-mono text-xs truncate">{f}</span>
                    </div>
                    {!isReadOnly && f !== "SKILL.md" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                        onClick={() => deleteFileMutation.mutate(f)}
                        disabled={deleteFileMutation.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground mb-4">
                No additional files yet.
              </p>
            )}

            {/* Upload controls */}
            {!isReadOnly && (
              <div className="flex flex-wrap gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    handleFileUpload(e.target.files);
                    e.target.value = "";
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadFileMutation.isPending}
                >
                  <Upload className="h-3.5 w-3.5 mr-1" />
                  {uploadFileMutation.isPending
                    ? "Uploading..."
                    : "Upload Files"}
                </Button>

                <input
                  ref={zipInputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => {
                    handleZipUpload(e.target.files);
                    e.target.value = "";
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => zipInputRef.current?.click()}
                  disabled={uploadZipMutation.isPending}
                >
                  <Archive className="h-3.5 w-3.5 mr-1" />
                  {uploadZipMutation.isPending
                    ? "Extracting..."
                    : "Upload Zip Package"}
                </Button>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-2">
              Upload individual files (.md, .py, .json, etc.) or a .zip
              archive containing the full skill directory structure.
            </p>
          </Section>
        )}

        {/* PREVIEW */}
        {form.instructions && (
          <Section title="SKILL.MD PREVIEW">
            <pre className="text-xs font-mono bg-muted/50 rounded-lg p-4 overflow-auto max-h-64 whitespace-pre-wrap">
              {`---\nname: ${form.name || "(unnamed)"}\ndescription: ${form.description || "(no description)"}\nversion: ${form.version}\nlicense: ${form.license}\ntags: [${form.tags.join(", ")}]\ncompatibility: ${form.compatibility || "(universal)"}\n---\n\n${form.instructions}`}
            </pre>
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
