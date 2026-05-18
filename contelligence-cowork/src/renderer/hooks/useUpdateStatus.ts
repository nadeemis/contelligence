import { useEffect, useState } from "react";
import type { UpdateStatus } from "@/types/electron";

const INITIAL: UpdateStatus = {
  state: "idle",
  currentVersion: "",
};

/**
 * Subscribes to update status from the Electron main process.
 * Returns the current status plus action helpers.
 *
 * In a non-Electron environment (e.g., the web build), the hook
 * stays in the "idle" state and all actions are no-ops.
 */
export function useUpdateStatus() {
  const [status, setStatus] = useState<UpdateStatus>(INITIAL);

  useEffect(() => {
    const api = window.electronAPI?.update;
    if (!api) return;
    let cancelled = false;
    api.getStatus().then((s) => {
      if (!cancelled) setStatus(s);
    });
    const unsubscribe = api.onStatusChanged((s) => setStatus(s));
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const api = window.electronAPI?.update;

  return {
    status,
    isAvailable: status.state === "available",
    checkNow: async () => {
      if (!api) return status;
      const next = await api.checkNow();
      setStatus(next);
      return next;
    },
    openRelease: () => api?.openRelease(),
    openDownloads: () => api?.openDownloads(),
  };
}
