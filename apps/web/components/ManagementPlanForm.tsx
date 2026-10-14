"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { fieldErrors } from "@/lib/bdmTravel";
import { monthLabel, monthsBetween, planHref, PLANS_API } from "@/lib/managementPlans";
import { useHydrated } from "@/lib/useHydrated";

// mgmt-026 (PN2): plan a month -- this IST month or one of the next 12 (`first`..`last`, from the API) that has no plan yet. The API
// checks the window again and answers a month planned meanwhile with a 409.
export default function ManagementPlanForm({ first, last, planned }: { first: string; last: string; planned: string[] }) {
  const router = useRouter();
  const ready = useHydrated();
  const months = monthsBetween(first, last).filter((m) => !planned.includes(m));
  const [month, setMonth] = useState(months[0] ?? "");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sending = useRef(false); // one plan per double click

  if (months.length === 0) return <p className="muted">Every month you can plan already has a plan.</p>;

  async function save() {
    if (sending.current || !month) return;
    sending.current = true;
    setBusy(true);
    setMessage("");
    const saved = await sendJson(PLANS_API, "POST", { month });
    if (!saved.ok) {
      setMessage(fieldErrors(saved.detail).month ?? saved.message);
      sending.current = false;
      setBusy(false);
      return;
    }
    router.push(planHref(month));
  }

  return (
    <form className="form action-card" noValidate aria-label="Plan a month" onSubmit={(e) => { e.preventDefault(); void save(); }} style={{ marginBottom: 18 }}>
      <fieldset disabled={!ready || busy} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        <div className="field">
          <label htmlFor="plan-month">Month</label>
          <select id="plan-month" value={month} onChange={(e) => setMonth(e.target.value)} aria-describedby={message ? "plan-month-error" : undefined}>
            {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
          {message && <p className="form-error" id="plan-month-error" role="alert">{message}</p>}
        </div>
        <div className="actions">
          <button className="btn" type="submit">{busy ? "Creating…" : "Plan this month"}</button>
        </div>
      </fieldset>
    </form>
  );
}
