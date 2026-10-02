import { useCallback, useEffect, useRef, useState } from "react";

// AGN-007 browser QA-02 (2026-10-02): focusing "on the next animation frame" missed controls in a real browser, because React can
// commit a state change made after an await later than that frame (the button to focus was not rendered yet). Ask here instead:
// focus is applied after the next commit, to the first id that exists, then forgotten.
export function useFocusAfterRender(): (...ids: string[]) => void {
  const pending = useRef<string[] | null>(null);
  const [, setRequest] = useState(0);

  useEffect(() => {
    const ids = pending.current;
    if (!ids) return;
    pending.current = null;
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) return el.focus();
    }
  });

  return useCallback((...ids: string[]) => {
    pending.current = ids;
    setRequest((n) => n + 1); // guarantees a commit even when nothing else changed
  }, []);
}
