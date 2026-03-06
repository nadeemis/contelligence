import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { skillsApi } from "@/lib/api";
import type { SkillSummary } from "@/types";

interface ChatSkillPickerProps {
  selected: string[];
  onSelectionChange: (ids: string[]) => void;
}

export function ChatSkillPicker({
  selected,
  onSelectionChange,
}: ChatSkillPickerProps) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ["skills-active"],
    queryFn: () => skillsApi.list({ status: "active" }),
  });

  // Also include built-in skills
  const { data: builtInSkills = [] } = useQuery({
    queryKey: ["skills-builtin"],
    queryFn: () => skillsApi.list({ status: "built-in" }),
  });

  const allSkills = [...builtInSkills, ...skills];

  const toggle = (name: string) => {
    onSelectionChange(
      selected.includes(name)
        ? selected.filter((s) => s !== name)
        : [...selected, name],
    );
  };

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary/50 transition-colors rounded-t-lg"
      >
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium text-foreground">Skills</span>
          <Badge variant="secondary" className="text-xs">
            {selected.length} selected
          </Badge>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-border space-y-3">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : allSkills.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No active skills available.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {allSkills.map((skill: SkillSummary) => (
                <SkillCard
                  key={skill.id}
                  skill={skill}
                  checked={selected.includes(skill.name)}
                  onToggle={() => toggle(skill.name)}
                />
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7"
              onClick={() =>
                onSelectionChange(allSkills.map((s) => s.name))
              }
            >
              Select All
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7"
              onClick={() => onSelectionChange([])}
            >
              Clear
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 ml-auto"
              onClick={() => navigate("/skills")}
            >
              Manage Skills &rarr;
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function SkillCard({
  skill,
  checked,
  onToggle,
}: {
  skill: SkillSummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={`flex items-start gap-2 rounded-lg border p-3 cursor-pointer transition-colors min-w-[140px] max-w-[180px] ${
        checked
          ? "border-primary/50 bg-primary/5"
          : "border-border bg-muted/30 hover:border-muted-foreground/30"
      }`}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={onToggle}
        className="mt-0.5"
      />
      <div className="min-w-0">
        <p className="text-xs font-mono font-medium text-foreground truncate">
          {skill.name}
        </p>
        <p className="text-[10px] text-muted-foreground leading-tight line-clamp-2">
          {skill.description}
        </p>
      </div>
    </label>
  );
}
