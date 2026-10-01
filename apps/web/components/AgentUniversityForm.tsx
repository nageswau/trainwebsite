"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { type AgentUniversity, buildUniversityPayload, changedOnly, LIMITS, UNIVERSITIES_URL, type UniversityDraft, validateUniversityDraft } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-049 D1): a Master adds or edits one of the agency's own universities. The server re-checks everything.
const FIELDS: { key: keyof UniversityDraft; label: string; limit: number }[] = [
  { key: "name", label: "Name (required)", limit: LIMITS.name },
  { key: "country", label: "Country (required)", limit: LIMITS.country },
  { key: "city", label: "City", limit: LIMITS.city },
];

const toDraft = (u?: AgentUniversity): UniversityDraft => ({ name: u?.name ?? "", country: u?.country ?? "", city: u?.city ?? "", entryRequirements: u?.entry_requirements ?? "" });

export default function AgentUniversityForm({ mode, university, onCancel, onSaved }: { mode: "add" | "edit"; university?: AgentUniversity; onCancel: () => void; onSaved: (u: AgentUniversity) => void }) {
  const idPrefix = `uni-${useId().replace(/:/g, "")}`;
  const [draft, setDraft] = useState<UniversityDraft>(() => toDraft(university));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const title = mode === "add" ? "Add university" : `Edit ${university?.name}`;

  useEffect(() => {
    document.getElementById(`${idPrefix}-title`)?.focus();
  }, [idPrefix]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = validateUniversityDraft(draft);
    if (problem) return setFailure(problem);
    const payload = buildUniversityPayload(draft);
    const body = mode === "add" ? payload : changedOnly(payload, buildUniversityPayload(toDraft(university)));
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "add" ? UNIVERSITIES_URL : `${UNIVERSITIES_URL}/${university!.id}`, {
        method: mode === "add" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.university) return setFailure(detailMessage(data?.detail, "Unable to save the university."));
      onSaved(data.university);
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation();
      onCancel();
    }
  }

  return (
    <form className="form card" onSubmit={submit} onKeyDown={onKeyDown} aria-busy={busy} noValidate aria-label={mode === "add" ? "Add university" : "Edit university"}>
      <h4 id={`${idPrefix}-title`} tabIndex={-1}>
        {title}
      </h4>
      {FIELDS.map((f) => (
        <div className="field" key={f.key}>
          <label htmlFor={`${idPrefix}-${f.key}`}>{f.label}</label>
          <input id={`${idPrefix}-${f.key}`} value={draft[f.key]} maxLength={f.limit} aria-required={f.label.includes("required") || undefined} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} />
        </div>
      ))}
      <div className="field">
        <label htmlFor={`${idPrefix}-req`}>Entry requirements</label>
        <textarea id={`${idPrefix}-req`} rows={3} maxLength={LIMITS.entry_requirements} value={draft.entryRequirements} onChange={(e) => setDraft({ ...draft, entryRequirements: e.target.value })} />
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      <button type="submit" className="btn small" disabled={busy}>
        {busy ? "Saving…" : "Save university"}
      </button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
    </form>
  );
}
