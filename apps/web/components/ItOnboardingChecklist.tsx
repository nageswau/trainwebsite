"use client";

import { useCallback, useEffect, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { onboardingUrl, type ChecklistItem } from "@/lib/itConversion";

/** itc-011 (C1): an enrolment's onboarding checklist, copied from the IT template at conversion. The student's IT counselor and the IT
 *  Admin tick items (`canTick`); the API decides who may. A failed tick keeps the old state and says so. */
export default function ItOnboardingChecklist({ enrollmentId, canTick, initial }: { enrollmentId: string; canTick: boolean; initial?: ChecklistItem[] }) {
  const [items, setItems] = useState<ChecklistItem[] | null>(initial ?? null);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setFailed(false);
    const response = await fetch(onboardingUrl(enrollmentId)).catch(() => null);
    const data = response?.ok ? ((await response.json().catch(() => null)) as { items?: ChecklistItem[] } | null) : null;
    if (!Array.isArray(data?.items)) return setFailed(true);
    setItems(data.items);
  }, [enrollmentId]);

  useEffect(() => {
    if (!initial) void load();
  }, [initial, load]);

  async function tick(item: ChecklistItem, done: boolean) {
    const before = items;
    setItems((list) => list && list.map((i) => (i.id === item.id ? { ...i, done } : i))); // QA11-01: shown at once, undone on a refusal
    setBusyId(item.id);
    setNotice(null);
    const outcome = await sendJson(onboardingUrl(enrollmentId, item.id), "PATCH", { done });
    setBusyId(null);
    const next = outcome.ok ? (outcome.data as { items?: ChecklistItem[] }).items : undefined;
    if (!outcome.ok || !Array.isArray(next)) {
      setItems(before);
      return setNotice(outcome.ok ? "Unable to update the checklist." : outcome.message);
    }
    setItems(next);
  }

  const done = items?.filter((i) => i.done).length ?? 0;
  return (
    <section aria-labelledby={`onboarding-${enrollmentId}`}>
      <h3 id={`onboarding-${enrollmentId}`} style={{ margin: 0 }}>Onboarding checklist</h3>
      {failed ? (
        <p className="form-error" role="alert" style={{ margin: "6px 0 0" }}>
          Couldn&apos;t load the checklist. <button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button>
        </p>
      ) : items === null ? (
        <p className="muted" style={{ margin: "6px 0 0" }}>Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ margin: "6px 0 0" }}>This enrolment has no checklist items.</p>
      ) : (
        <>
          <p className="muted" style={{ margin: "6px 0", fontSize: 13 }}>{done} of {items.length} done</p>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
            {items.map((item) => (
              <li key={item.id}>
                <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={item.done} disabled={!canTick || busyId !== null} onChange={(e) => void tick(item, e.target.checked)} />
                  <span>{item.label}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      {notice && <p className="form-error" role="alert" style={{ margin: "6px 0 0", fontSize: 13 }}>{notice}</p>}
    </section>
  );
}
