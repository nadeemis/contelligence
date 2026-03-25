import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { TriggerConfig, TriggerType } from "@/types";

const TRIGGER_OPTIONS: { value: TriggerType; label: string; description: string }[] = [
  { value: "cron", label: "Cron", description: "Standard cron expression" },
  { value: "interval", label: "Interval", description: "Every N minutes" },
  { value: "event", label: "Event", description: "Azure Event Grid trigger" },
  { value: "webhook", label: "Webhook", description: "External HTTP trigger" },
];

const TIMEZONE_OPTIONS = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
];

interface TriggerTypeSelectorProps {
  value: TriggerConfig;
  onChange: (trigger: TriggerConfig) => void;
}

export function TriggerTypeSelector({ value, onChange }: TriggerTypeSelectorProps) {
  return (
    <div className="space-y-4">
      <Label className="text-muted-foreground">Trigger Type</Label>
      <RadioGroup
        value={value.type}
        onValueChange={(type) => onChange({ ...value, type: type as TriggerType })}
        className="grid grid-cols-2 gap-3"
      >
        {TRIGGER_OPTIONS.map((opt) => (
          <Label
            key={opt.value}
            htmlFor={`trigger-${opt.value}`}
            className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
              value.type === opt.value
                ? "border-primary bg-primary/5"
                : "border-border hover:bg-secondary/50"
            }`}
          >
            <RadioGroupItem value={opt.value} id={`trigger-${opt.value}`} className="mt-0.5" />
            <div>
              <div className="text-sm font-medium text-foreground">{opt.label}</div>
              <div className="text-xs text-muted-foreground">{opt.description}</div>
            </div>
          </Label>
        ))}
      </RadioGroup>

      {/* Type-specific fields */}
      <div className="space-y-3 pl-1">
        {value.type === "cron" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-sm">Cron Expression</Label>
              <Input
                value={value.cron ?? ""}
                onChange={(e) => onChange({ ...value, cron: e.target.value })}
                placeholder="0 6 * * 1-5"
                className="bg-secondary border-border text-foreground font-mono"
              />
              {value.cron && (
                <p className="text-xs text-muted-foreground">
                  Format: minute hour day-of-month month day-of-week
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-sm">Timezone</Label>
              <Select
                value={value.timezone ?? "UTC"}
                onValueChange={(v) => onChange({ ...value, timezone: v })}
              >
                <SelectTrigger className="bg-secondary border-border text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <SelectItem key={tz} value={tz}>{tz}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {value.type === "interval" && (
          <div className="space-y-1.5">
            <Label className="text-muted-foreground text-sm">Interval (minutes)</Label>
            <Input
              type="number"
              value={value.interval_minutes?.toString() ?? ""}
              onChange={(e) => onChange({ ...value, interval_minutes: parseInt(e.target.value) || undefined })}
              placeholder="360"
              className="bg-secondary border-border text-foreground w-40"
            />
          </div>
        )}

        {value.type === "event" && (
          <>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-sm">Event Source</Label>
              <Input
                value={value.event_source ?? ""}
                onChange={(e) => onChange({ ...value, event_source: e.target.value })}
                placeholder="blob:vendor-inbox"
                className="bg-secondary border-border text-foreground"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-sm">Event Filter (glob/regex)</Label>
              <Input
                value={value.event_filter ?? ""}
                onChange={(e) => onChange({ ...value, event_filter: e.target.value })}
                placeholder="*.pdf"
                className="bg-secondary border-border text-foreground"
              />
            </div>
          </>
        )}

        {value.type === "webhook" && (
          <div className="space-y-1.5">
            <Label className="text-muted-foreground text-sm">Webhook Secret (for HMAC validation)</Label>
            <Input
              type="password"
              value={value.webhook_secret ?? ""}
              onChange={(e) => onChange({ ...value, webhook_secret: e.target.value })}
              placeholder="whsec_..."
              className="bg-secondary border-border text-foreground"
            />
          </div>
        )}
      </div>
    </div>
  );
}
