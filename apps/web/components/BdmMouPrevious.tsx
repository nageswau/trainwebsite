"use client";
import { type SyntheticEvent, useState } from "react";

import { isPage } from "@/lib/apiErrors";
import { MOUS_URL, type MouRow, mouDocumentUrl, mousQuery } from "@/lib/bdmMous";
import { formatCalendarDate } from "@/lib/formatDate";

// bdm-005 (M6): MoUs replaced by a renewal, read the first time the section is opened. Each keeps its own scoped download.
export default function BdmMouPrevious({ orgId }: { orgId: string }) {
  const [rows, setRows] = useState<MouRow[] | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "failed">("idle");

  async function load() {
    setState("loading");
    const response = await fetch(`${MOUS_URL}?${mousQuery({ organization: orgId, current: false })}`).catch(() => null);
    const data: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (!isPage<MouRow>(data)) return setState("failed");
    setRows(data.items);
    setState("ready");
  }
  const opened = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (event.currentTarget.open && state === "idle") void load();
  };

  return (
    <details onToggle={opened}>
      <summary>Previous MoUs</summary>
      {state === "failed" ? (
        <p className="muted">
          Unable to load the previous MoUs.{" "}
          <button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button>
        </p>
      ) : rows === null ? (
        <p className="muted" aria-live="polite">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No previous MoUs.</p>
      ) : (
        <ul aria-label="Previous MoUs">
          {rows.map((m) => {
            const name = m.reference ?? `MoU of ${formatCalendarDate(m.status_changed_at)}`;
            return (
              <li key={m.id}>
                {name} · {m.status_label}
                {m.valid_until ? ` · valid until ${formatCalendarDate(m.valid_until)}` : ""}
                {m.has_document && (
                  <>
                    {" "}
                    <a href={mouDocumentUrl(m.id)} download aria-label={`Download ${name}`}>Download</a>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </details>
  );
}
