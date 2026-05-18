import { useState, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { History, Search, Trash2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { InputHistoryEntry } from "@/hooks/useInputHistory";

interface HistoryDropdownProps {
  history: InputHistoryEntry[];
  onSelect: (text: string) => void;
  onClear: () => void;
}

export function HistoryDropdown({ history, onSelect, onClear }: HistoryDropdownProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [popupStyle, setPopupStyle] = useState<React.CSSProperties>({});

  // Compute popup position relative to viewport when opening
  useEffect(() => {
    if (!open || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setPopupStyle({
      position: "fixed",
      bottom: window.innerHeight - rect.top + 8,
      left: rect.left,
      width: 320,
      maxHeight: 288,
    });
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        containerRef.current && !containerRef.current.contains(target) &&
        popupRef.current && !popupRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus search input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Keyboard shortcut: Cmd/Ctrl+H
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "h") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const filtered = searchQuery.trim()
    ? history.filter((e) => e.text.toLowerCase().includes(searchQuery.toLowerCase()))
    : history;

  // Show most recent first
  const displayed = [...filtered].reverse().slice(0, 50);

  const handleSelect = useCallback(
    (text: string) => {
      onSelect(text);
      setOpen(false);
      setSearchQuery("");
    },
    [onSelect],
  );

  if (history.length === 0) return null;

  return (
    <div ref={containerRef} className="relative inline-flex">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground"
            onClick={() => setOpen((v) => !v)}
          >
            <History className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">Input history (⌘H)</TooltipContent>
      </Tooltip>

      {open && createPortal(
        <div ref={popupRef} style={popupStyle} className="rounded-lg border border-border bg-card shadow-lg overflow-hidden z-[100] flex flex-col">
          {/* Search bar */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
            <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search history..."
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => {
                    onClear();
                    setOpen(false);
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">Clear all history</TooltipContent>
            </Tooltip>
          </div>

          {/* Entries list */}
          <div className="overflow-y-auto flex-1">
            {displayed.length === 0 ? (
              <p className="text-xs text-muted-foreground px-3 py-4 text-center">
                {searchQuery ? "No matches found" : "No history yet"}
              </p>
            ) : (
              displayed.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => handleSelect(entry.text)}
                  className="w-full text-left px-3 py-2 text-xs text-foreground hover:bg-secondary/60 transition-colors border-b border-border/50 last:border-0"
                  title={entry.text}
                >
                  <span className="line-clamp-2">{entry.text}</span>
                  <span className="text-[10px] text-muted-foreground mt-0.5 block">
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                </button>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-3 py-1.5 border-t border-border text-[10px] text-muted-foreground">
            {history.length} entries · Click to insert
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
