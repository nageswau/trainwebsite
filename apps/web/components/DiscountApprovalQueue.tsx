"use client";

import { useEffect, useState } from "react";

import { money } from "@/components/FeeAccountSummary";
import { sendJson } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { DISCOUNT_QUEUE_URL, decideUrl, type DiscountRequest } from "@/lib/feeDiscounts";

/** itc-014 (DEC-SCOPE-363): the IT Admin Payments page's approval queue for discount requests (`discounts.approve`). Rejecting needs a
 *  note; the caller's own request has no buttons -- the API refuses self-approval too (AC3). */
export default function DiscountApprovalQueue() {
  const [items, setItems] = useState<DiscountRequest[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    fetch(DISCOUNT_QUEUE_URL, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        const data = await r.json();
        if (!Array.isArray(data)) throw new Error("shape");
        setItems(data);
      })
      .catch(() => setLoadError(true));
  }, []);

  async function decide(item: DiscountRequest, verb: "approve" | "reject") {
    if (busy) return;
    const note = (notes[item.id] ?? "").trim();
    if (verb === "reject" && !note) return setErrors({ ...errors, [item.id]: "Give a reason for rejecting." });
    setBusy(item.id);
    setErrors({ ...errors, [item.id]: "" });
    setNotice("");
    const outcome = await sendJson(decideUrl(item.id, verb), "POST", note ? { note } : {});
    setBusy(null);
    if (!outcome.ok) return setErrors({ ...errors, [item.id]: outcome.message });
    setItems((current) => (current ?? []).filter((i) => i.id !== item.id));
    const name = item.student.full_name;
    setNotice(verb === "approve" ? `Discount approved for ${name}. The fee balance is updated.` : `Discount rejected for ${name}.`);
  }

  return (
    <section aria-labelledby="discount-queue-heading" className="action-card" style={{ display: "grid", gap: 12 }}>
      <h3 id="discount-queue-heading" style={{ margin: 0 }}>Discount approvals</h3>
      <p className="muted" style={{ margin: 0 }}>
        Discounts and waivers requested by counselors and accounts staff. An approved discount lowers the fee still owed; you can&apos;t
        decide a request you made yourself.
      </p>
      {loadError ? (
        <p className="form-error" role="alert" style={{ margin: 0 }}>The discount requests could not be loaded. Refresh the page to try again.</p>
      ) : items === null ? (
        <p className="muted" role="status" style={{ margin: 0 }}>Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No discount requests are waiting for approval.</p>
      ) : (
        <ul aria-label="Discount requests waiting for approval" className="list-clean" style={{ display: "grid", gap: 12, margin: 0 }}>
          {items.map((i) => {
            const name = i.student.full_name;
            const noteId = `discount-note-${i.id}`;
            return (
              <li key={i.id} style={{ display: "grid", gap: 6, fontSize: 14 }}>
                <strong>{[name, i.enrollment_code, i.course].filter(Boolean).join(" · ")}</strong>
                <span>{money("INR", i.amount)} off · {i.reason} · asked by {i.requested_by.full_name} on {formatCalendarDate(i.created_at)}</span>
                {i.own ? (
                  <span className="muted">Your request — another approver must decide it.</span>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                    <div className="field" style={{ marginBottom: 0, flex: "1 1 14rem" }}>
                      <label htmlFor={noteId}>Note for {name}</label>
                      <input id={noteId} type="text" maxLength={500} value={notes[i.id] ?? ""} disabled={busy === i.id}
                        onChange={(e) => setNotes({ ...notes, [i.id]: e.target.value })} placeholder="Required to reject" />
                    </div>
                    <button type="button" className="btn small" disabled={busy === i.id} aria-label={`Approve discount for ${name}`} onClick={() => decide(i, "approve")}>Approve</button>
                    <button type="button" className="btn secondary small" disabled={busy === i.id} aria-label={`Reject discount for ${name}`} onClick={() => decide(i, "reject")}>Reject</button>
                  </div>
                )}
                {errors[i.id] && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{errors[i.id]}</p>}
              </li>
            );
          })}
        </ul>
      )}
      {notice && <p className="form-message" role="status" style={{ margin: 0, fontSize: 13 }}>{notice}</p>}
    </section>
  );
}
