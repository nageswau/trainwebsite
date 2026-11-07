"use client";
import { useEffect, useState } from "react";

import RecruiterMessages from "@/components/RecruiterMessages";
import { COMPANIES_URL, type CompanyPermissions } from "@/lib/recruiterCompanies";

/** pob-023 (G12, QA-07): messages to a requirement's company contacts. Reading a requirement does not imply reading its company: an assignee
 *  or backup owner can be outside the company's scope, so the section appears only for a caller the company itself admits, and writes follow
 *  the company's right -- the rule the API applies to a send. */
export default function RecruiterRequirementMessages({ companyId, jobId }: { companyId: string; jobId: string }) {
  const [state, setState] = useState<{ canWrite: boolean } | "loading" | "hidden" | "failed">("loading");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    fetch(`${COMPANIES_URL}/${encodeURIComponent(companyId)}`, { signal: controller.signal })
      .then(async (r) => {
        if (r.status === 403 || r.status === 404) return setState("hidden");
        if (!r.ok) throw new Error(String(r.status));
        const body: { company: { permissions: CompanyPermissions } } = await r.json();
        setState({ canWrite: body.company.permissions.can_edit });
      })
      .catch(() => controller.signal.aborted || setState("failed"));
    return () => controller.abort();
  }, [companyId, version]);

  if (state === "hidden") return null;
  if (state === "loading") return <p className="muted" role="status" style={{ fontSize: 13 }}>Loading messages…</p>;
  if (state === "failed") {
    return (
      <div>
        <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load the messages.</p>
        <button type="button" className="btn secondary small" onClick={() => setVersion((n) => n + 1)}>Retry</button>
      </div>
    );
  }
  return <RecruiterMessages source={{ kind: "requirement", companyId, jobId }} canWrite={state.canWrite} />;
}
