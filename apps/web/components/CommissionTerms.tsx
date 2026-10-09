"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import CommissionTermForm from "@/components/CommissionTermForm";
import { sendRequest } from "@/lib/apiErrors";
import { type CommissionTerm, rateText, scopeText, termsUrl } from "@/lib/commissionTerms";
import type { Agreement, AgreementOptions } from "@/lib/universityAgreements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-016 (§15): an agreement's commission terms -- RESTRICTED (U2). The agreement card renders this only when the API sent
// `commission_terms`, which it does for the commission roles alone. Add / Edit / Remove follow the API's flags (CM8, CM9); every success
// re-reads the page (router.refresh). Texts are data only.
const REMOVE_FAILED = "The commission term could not be removed. Try again.";

export default function CommissionTerms({ agreement, terms, options }: { agreement: Agreement; terms: CommissionTerm[]; options: AgreementOptions | null }) {
  const router = useRouter();
  const sending = useRef(false);
  const [open, setOpen] = useState<string | null>(null); // "new", "<id>:edit", "<id>:remove", or null
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const headingId = `ct-${agreement.id}-heading`;
  const addId = `ct-${agreement.id}-add`;
  const canAdd = agreement.permissions.can_edit_terms && options !== null;

  const show = (key: string | null) => {
    setOpen(key);
    setFailure(null);
    setNotice(null);
  };
  const done = (message: string) => {
    show(null);
    setNotice(message);
    focus(addId, headingId); // the control that had focus is gone
    router.refresh();
  };
  async function remove(term: CommissionTerm) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(termsUrl(agreement.id, term.id), { method: "DELETE" });
    sending.current = false;
    setBusy(false);
    if (outcome.ok) return done("Commission term removed.");
    setFailure(outcome.status !== undefined && outcome.detail === undefined ? REMOVE_FAILED : outcome.message);
  }

  return (
    <section aria-label={`Commission terms of ${agreement.mou_number} (restricted)`} style={{ borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 8, display: "grid", gap: 8 }}>
      <h4 id={headingId} tabIndex={-1} style={{ margin: 0 }}>Commission terms <span className="badge">Restricted</span></h4>
      {terms.length === 0 && open !== "new" && <p className="muted" style={{ margin: 0 }}>No commission terms recorded yet.</p>}
      {terms.length > 0 && (
        <ol className="list-clean" style={{ display: "grid", gap: 8, margin: 0 }}>
          {terms.map((t, i) => {
            const name = `commission term ${i + 1}`;
            return (
              <li key={t.id} style={{ display: "grid", gap: 4 }}>
                <p style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                  <strong>{rateText(t)}</strong>
                  <span className="muted">{`${t.currency} · ${t.trigger_label}`}</span>
                </p>
                <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "4px 16px", margin: 0 }}>
                  {([["Applies to", scopeText(t)], ["Conditions", t.conditions], ["Payment timeline", t.payment_timeline], ["Payment terms", t.payment_terms]] as const)
                    .filter(([, value]) => value)
                    .map(([term, value]) => [
                      <dt key={`${term}-t`} className="muted">{term}</dt>,
                      <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value}</dd>,
                    ])}
                </dl>
                {t.permissions.can_edit && options && open !== `${t.id}:edit` && (
                  <div className="actions">
                    <button type="button" className="btn ghost small" onClick={() => show(`${t.id}:edit`)} disabled={busy}>
                      Edit<span className="visually-hidden"> {name}</span>
                    </button>
                    <button type="button" className="btn ghost small" onClick={() => show(`${t.id}:remove`)} disabled={busy}>
                      Remove<span className="visually-hidden"> {name}</span>
                    </button>
                  </div>
                )}
                {open === `${t.id}:remove` && (
                  <div className="actions" role="group" aria-label={`Remove ${name}?`}>
                    <span>Remove this commission term?</span>
                    <button type="button" className="btn small" onClick={() => void remove(t)} disabled={busy} autoFocus>{busy ? "Removing…" : "Yes, remove"}</button>
                    <button type="button" className="btn secondary small" onClick={() => show(null)} disabled={busy}>Cancel</button>
                  </div>
                )}
                {open === `${t.id}:edit` && options && (
                  <CommissionTermForm agreementId={agreement.id} options={options} term={t} label={`Edit ${name}`} onSaved={done} onCancel={() => show(null)} />
                )}
              </li>
            );
          })}
        </ol>
      )}
      {canAdd && (open === "new" ? (
        <CommissionTermForm agreementId={agreement.id} options={options} label="New commission term" onSaved={done} onCancel={() => show(null)} />
      ) : (
        <div><button id={addId} type="button" className="btn secondary small" onClick={() => show("new")} disabled={busy}>Add commission term</button></div>
      ))}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}
