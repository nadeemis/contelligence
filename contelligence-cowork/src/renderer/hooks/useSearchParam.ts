import { useSearchParams } from "react-router-dom";
import { useCallback } from "react";

/**
 * A hook that syncs a single URL search parameter with component state.
 * Returns [value, setValue] similar to useState.
 */
export function useSearchParam(
  key: string,
  defaultValue = ""
): [string, (value: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? defaultValue;

  const setValue = useCallback(
    (newValue: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (newValue === "" || newValue === defaultValue) {
            next.delete(key);
          } else {
            next.set(key, newValue);
          }
          return next;
        },
        { replace: true }
      );
    },
    [key, defaultValue, setSearchParams]
  );

  return [value, setValue];
}
