import { useState, useEffect, useCallback, useRef } from "react";

export interface InputHistoryEntry {
  id: string;
  text: string;
  sessionId: string;
  timestamp: number;
}

export interface InputHistoryStore {
  version: 1;
  entries: InputHistoryEntry[];
}

const MAX_ENTRIES = 500;
const MAX_TEXT_LENGTH = 10_000;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Hook managing chat input history with persistence via Electron IPC.
 * Provides add, search, clear, and keyboard-navigation helpers.
 */
export function useInputHistory() {
  const [history, setHistory] = useState<InputHistoryEntry[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [draft, setDraft] = useState("");
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load persisted history on mount
  useEffect(() => {
    window.electronAPI?.getInputHistory?.().then((store) => {
      if (store && Array.isArray(store.entries)) {
        setHistory(store.entries);
      }
    });
  }, []);

  // Debounced persist to disk
  const persistHistory = useCallback((entries: InputHistoryEntry[]) => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      const store: InputHistoryStore = { version: 1, entries };
      window.electronAPI?.saveInputHistory?.(store);
    }, 1000);
  }, []);

  // Add a new entry after sending a message
  const addEntry = useCallback(
    (text: string, sessionId: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Truncate if too long
      const stored = trimmed.length > MAX_TEXT_LENGTH ? trimmed.slice(0, MAX_TEXT_LENGTH) : trimmed;

      // Deduplication: skip if last entry is identical
      setHistory((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].text === stored) {
          return prev;
        }

        const entry: InputHistoryEntry = {
          id: generateId(),
          text: stored,
          sessionId,
          timestamp: Date.now(),
        };

        // FIFO cap
        const next = [...prev, entry].slice(-MAX_ENTRIES);
        persistHistory(next);
        return next;
      });

      // Reset navigation state
      setHistoryIndex(-1);
      setDraft("");
    },
    [persistHistory],
  );

  // Search/filter history entries
  const search = useCallback(
    (query: string): InputHistoryEntry[] => {
      if (!query.trim()) return history;
      const lower = query.toLowerCase();
      return history.filter((e) => e.text.toLowerCase().includes(lower));
    },
    [history],
  );

  // Clear all history
  const clearHistory = useCallback(() => {
    setHistory([]);
    setHistoryIndex(-1);
    setDraft("");
    window.electronAPI?.clearInputHistory?.();
  }, []);

  // Navigate up in history (older)
  const navigateUp = useCallback(
    (currentInput: string): string | null => {
      if (history.length === 0) return null;

      if (historyIndex === -1) {
        // Stash current input as draft
        setDraft(currentInput);
        const newIndex = history.length - 1;
        setHistoryIndex(newIndex);
        return history[newIndex].text;
      }

      if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        return history[newIndex].text;
      }

      // Already at oldest entry
      return null;
    },
    [history, historyIndex],
  );

  // Navigate down in history (newer)
  const navigateDown = useCallback((): string | null => {
    if (historyIndex === -1) return null;

    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      return history[newIndex].text;
    }

    // Back to draft
    setHistoryIndex(-1);
    return draft;
  }, [history, historyIndex, draft]);

  // Cancel navigation, restore draft
  const cancelNavigation = useCallback((): string => {
    setHistoryIndex(-1);
    return draft;
  }, [draft]);

  const isBrowsing = historyIndex !== -1;
  const browsingPosition = isBrowsing
    ? { current: historyIndex + 1, total: history.length }
    : null;

  return {
    history,
    historyIndex,
    isBrowsing,
    browsingPosition,
    addEntry,
    search,
    clearHistory,
    navigateUp,
    navigateDown,
    cancelNavigation,
  };
}
