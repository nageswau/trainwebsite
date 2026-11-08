// pob-018 (DEC-SCOPE-428): where a candidate came from and when, when the details were last checked, how far outreach has got and
// how the candidate agreed to be represented. Labels are display only; the API decides every rule (A3-A7).
import type { LookupPage } from "@/lib/lookups";
import type { PersonRef } from "@/lib/telecallerLeads";

export const OUTREACH_STATUSES = [
  { key: "not_contacted", label: "Not contacted" }, { key: "contacted", label: "Contacted" }, { key: "responded", label: "Responded" },
  { key: "consented", label: "Consented" }, { key: "declined", label: "Declined" },
] as const;
export const PERMISSION_METHODS = [
  { key: "call", label: "Phone call" }, { key: "email", label: "Email" }, { key: "whatsapp", label: "WhatsApp" }, { key: "linkedin", label: "LinkedIn message" },
  { key: "in_person", label: "In person" }, { key: "form", label: "Signed form" }, { key: "other", label: "Other" },
] as const;
export type OutreachStatus = (typeof OUTREACH_STATUSES)[number]["key"];

export type NamedRef = { id: string; name: string };
export type CandidateSourcing = {
  source_date: string; referrer_name: string | null; referrer: { id: string | null; candidate_code: string | null; name: string } | null;
  vendor: NamedRef | null; institution: NamedRef | null; portal_import_reference: string | null; last_verified_on: string | null;
  last_verified_by: PersonRef | null; outreach_status: OutreachStatus; outreach_status_changed_at: string | null;
  permission: { method: string; given_on: string; note: string | null; recorded_by: PersonRef | null } | null; permitted: boolean;
};

export const labelFor = (options: readonly { key: string; label: string }[], key: string | null | undefined) => options.find((o) => o.key === key)?.label ?? key ?? "";

/** Today in IST (the office day the API checks dates against), as YYYY-MM-DD. */
export const istToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

/** The referrer picker: other pool candidates (the list route's name, code or email search). */
export function referrerSearch(excludeId: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "10" });
    if (q) query.set("q", q);
    const response = await fetch(`/api/v1/recruiter/candidates?${query}`, { signal });
    if (!response.ok) throw new Error(`Candidate search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; candidate_code: string; name: string }[]; total: number };
    const items = page.items.filter((c) => c.id !== excludeId).map((c) => ({ id: c.id, label: c.name, detail: c.candidate_code }));
    return { items, truncated: page.total > page.items.length };
  };
}

/** The vendor picker: the caller's vendor companies (pob-010 `relationship=vendor`). */
export async function vendorSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ relationship: "vendor", limit: "10" });
  if (q) query.set("q", q);
  const response = await fetch(`/api/v1/recruiter/companies?${query}`, { signal });
  if (!response.ok) throw new Error(`Vendor search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; name: string; code?: string | null }[]; total: number };
  return { items: page.items.map((c) => ({ id: c.id, label: c.name, detail: c.code ?? null })), truncated: page.total > page.items.length };
}
