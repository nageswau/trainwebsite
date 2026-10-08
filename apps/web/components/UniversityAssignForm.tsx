"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { managerSearch, type University, universityUrl } from "@/lib/universities";

// upc-003 (§27, UM3): the head (or super_admin) sets the primary manager and an optional backup in one save. The picker offers only the
// managers the API would accept; clearing the primary clears the backup too (a backup needs a primary).
const ref = (m: University["primary_manager"]): PickOption | null => (m ? { id: m.id, label: m.full_name } : null);

export default function UniversityAssignForm({ university: u }: { university: University }) {
  const router = useRouter();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [primary, setPrimary] = useState<PickOption | null>(ref(u.primary_manager));
  const [backup, setBackup] = useState<PickOption | null>(ref(u.backup_manager));
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(universityUrl(u.id, "assign"), "POST", {
      primary_manager_user_id: primary?.id ?? null, backup_manager_user_id: primary ? backup?.id ?? null : null,
    });
    sending.current = false;
    setBusy(false);
    if (outcome.ok) {
      setResult({ text: "Managers saved.", failed: false });
      router.refresh();
    } else setResult({ text: outcome.message, failed: true });
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 10 }} aria-label="Assign managers">
      <SearchableSelect id="assign-primary" label="Primary manager" noun="manager" search={managerSearch} initial={ref(u.primary_manager)} onChange={setPrimary} disabled={busy} />
      <SearchableSelect id="assign-backup" label="Backup manager" noun="manager" search={managerSearch} initial={ref(u.backup_manager)} onChange={setBackup}
        disabled={busy || !primary} />
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
        <button className="btn small" type="submit" disabled={busy}>{busy ? "Saving…" : "Save managers"}</button>
        {result && <span role={result.failed ? "alert" : "status"} className={result.failed ? "notice" : "muted"}>{result.text}</span>}
      </div>
    </form>
  );
}
