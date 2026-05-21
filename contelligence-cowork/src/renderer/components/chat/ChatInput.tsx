import { useState, useCallback, useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Send, Zap, ListPlus } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string, mode?: "immediate" | "enqueue") => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  externalValue?: string;
  onExternalValueConsumed?: () => void;
  onValueChange?: (value: string) => void;
  onNavigateUp?: (currentInput: string) => string | null;
  onNavigateDown?: () => string | null;
  onCancelNavigation?: () => string;
  isBrowsingHistory?: boolean;
  browsingPosition?: { current: number; total: number } | null;
  bottomLeftSlot?: React.ReactNode;
}

export function ChatInput({
  onSend,
  disabled = false,
  isStreaming = false,
  placeholder = "Type your instruction...",
  externalValue,
  onExternalValueConsumed,
  onValueChange,
  onNavigateUp,
  onNavigateDown,
  onCancelNavigation,
  isBrowsingHistory = false,
  browsingPosition,
  bottomLeftSlot,
}: ChatInputProps) {
  const [value, setValue] = useState("");

  // Notify parent of value changes for draft persistence
  useEffect(() => {
    onValueChange?.(value);
  }, [value, onValueChange]);

  // Accept value pushed in from parent (e.g. sample prompt click)
  useEffect(() => {
    if (externalValue !== undefined && externalValue !== "") {
      setValue(externalValue);
      onExternalValueConsumed?.();
      textareaRef.current?.focus();
    }
  }, [externalValue, onExternalValueConsumed]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const send = useCallback(
    (mode?: "immediate" | "enqueue") => {
      const trimmed = value.trim();
      if (!trimmed || disabled) return;
      onSend(trimmed, mode);
      setValue("");
    },
    [value, disabled, onSend],
  );

  // Auto-resize textarea to fit content, min 2 rows
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const minHeight = 2.5 * 16 * 1.5;
    el.style.height = `${Math.max(el.scrollHeight, minHeight)}px`;
  }, [value]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // History navigation: ArrowUp
      if (e.key === "ArrowUp" && onNavigateUp) {
        const el = textareaRef.current;
        // Only trigger if cursor is at start or input is empty
        if (el && (value === "" || el.selectionStart === 0)) {
          e.preventDefault();
          const result = onNavigateUp(value);
          if (result !== null) setValue(result);
        }
        return;
      }

      // History navigation: ArrowDown
      if (e.key === "ArrowDown" && onNavigateDown && isBrowsingHistory) {
        const el = textareaRef.current;
        // Only trigger if cursor is at end or input is single line
        if (el && (el.selectionStart === value.length || !value.includes("\n"))) {
          e.preventDefault();
          const result = onNavigateDown();
          if (result !== null) setValue(result);
        }
        return;
      }

      // History navigation: Escape to cancel
      if (e.key === "Escape" && onCancelNavigation && isBrowsingHistory) {
        e.preventDefault();
        const result = onCancelNavigation();
        setValue(result);
        return;
      }

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (isStreaming && (e.metaKey || e.ctrlKey)) {
          // Cmd/Ctrl+Enter while streaming → queue
          send("enqueue");
        } else if (isStreaming) {
          // Enter while streaming → steer
          send("immediate");
        } else {
          // Enter while idle → new turn (let parent decide)
          send();
        }
      }
    },
    [send, isStreaming, value, onNavigateUp, onNavigateDown, onCancelNavigation, isBrowsingHistory],
  );

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={2}
          className="flex-1 rounded-md border bg-card border-border text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          style={{ maxHeight: "12rem" }}
        />
        {isStreaming ? (
          <div className="flex gap-1 shrink-0 mb-0.5">
            <Button
              onClick={() => send("immediate")}
              disabled={disabled || !value.trim()}
              title="Steer (Enter): inject into the current turn"
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Zap className="h-4 w-4" />
            </Button>
            <Button
              onClick={() => send("enqueue")}
              disabled={disabled || !value.trim()}
              title="Queue (⌘/Ctrl+Enter): run after the current turn"
              variant="outline"
            >
              <ListPlus className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => send()}
            disabled={disabled || !value.trim()}
            className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0 mb-0.5"
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
      <div className="flex items-center min-h-[1.25rem] gap-2">
        {bottomLeftSlot}
        {isBrowsingHistory && browsingPosition ? (
          <div className="text-[10px] text-muted-foreground px-1">
            <kbd className="px-1 py-0.5 rounded bg-secondary">↑↓</kbd> history · {browsingPosition.current}/{browsingPosition.total} ·{" "}
            <kbd className="px-1 py-0.5 rounded bg-secondary">Esc</kbd> cancel
          </div>
        ) : isStreaming ? (
          <div className="text-[10px] text-muted-foreground px-1">
            <kbd className="px-1 py-0.5 rounded bg-secondary">Enter</kbd> steer ·{" "}
            <kbd className="px-1 py-0.5 rounded bg-secondary">⌘/Ctrl+Enter</kbd> queue ·{" "}
            <kbd className="px-1 py-0.5 rounded bg-secondary">Shift+Enter</kbd> newline
          </div>
        ) : (
          <div className="text-[10px] text-muted-foreground px-1 invisible">
            <kbd className="px-1 py-0.5 rounded bg-secondary">↑↓</kbd> history
          </div>
        )}
      </div>
    </div>
  );
}
