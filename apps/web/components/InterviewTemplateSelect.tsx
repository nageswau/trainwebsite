"use client";
import { useEffect, useState } from "react";

import { approvedEmailTemplates, type TemplateOption } from "@/lib/recruiterInterviews";

/** pob-022 (DEC-SCOPE-421 A1/A9): choose an approved email template, or the standard text. `kind` narrows the list (the interview
 * confirmation). While loading, or when the list cannot be read, only the standard text is offered -- nothing blocks the form. A chosen id
 * that is no longer approved stays listed, marked, so a saved setting is never silently changed. */
export default function InterviewTemplateSelect({ id, label, value, onChange, kind, error }: {
  id: string; label: string; value: string; onChange: (value: string) => void; kind?: string; error?: string;
}) {
  const [options, setOptions] = useState<TemplateOption[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    approvedEmailTemplates(controller.signal)
      .then((items) => setOptions(kind ? items.filter((t) => t.kind === kind) : items))
      .catch(() => !controller.signal.aborted && setFailed(true));
    return () => controller.abort();
  }, [kind]);
  const listed = options ?? [];
  const stale = value && options && !listed.some((t) => t.id === value);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={options === null && !failed} aria-busy={options === null && !failed}
        aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined}>
        <option value="">Standard text</option>
        {listed.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        {stale && <option value={value}>No longer approved — choose another</option>}
      </select>
      {options === null && !failed && <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading templates…</p>}
      {failed && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Templates could not be loaded; the standard text is used.</p>}
      {options !== null && !listed.length && <p className="muted" style={{ margin: 0, fontSize: 13 }}>No approved templates yet; the standard text is used.</p>}
      {error && <p id={`${id}-error`} className="form-error">{error}</p>}
    </div>
  );
}
