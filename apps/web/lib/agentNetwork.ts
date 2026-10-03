// AGN-022 (DEC-SCOPE-063): Overseas Admin's agent network -- the shapes the list and detail panels share. The server is the
// authority on access and on every figure; these only describe what it returns.

import { detailMessage, isPage, type Page } from "@/lib/apiErrors";

export const ORGS_URL = "/api/v1/overseas-admin/agent-orgs";
export const NETWORK_PATH = "/overseas/admin/agent-network";
export const PAGE_SIZE = 20;

export type OrgStatus = "pending" | "active" | "suspended" | "rejected";
export type NetworkMaster = { id: string; code: string; full_name: string; email: string; status: string };
export type NetworkCounts = { students: number; applications: number; enrollments: number };
export type NetworkOrg = {
  id: string;
  name: string;
  prefix: string;
  status: OrgStatus;
  created_at: string;
  masters: NetworkMaster[];
  staff_count: number;
  counts: NetworkCounts;
};
export type CommissionTotal = { currency: string; count: number; amount: number };
export type OrgDetail = NetworkOrg & {
  status_changed_at: string | null;
  commission: { claimable: CommissionTotal[]; claims: number; revenue: CommissionTotal[] };
  deposits: { currency: "INR"; count: number; collected: number; remitted: number; refunded: number };
  as_of: string;
};
export type NetworkStudent = { id: string; full_name: string | null; status: string; assigned_code: string | null; has_login: boolean; applications: number; created_at: string };
export type NetworkApplication = {
  id: string;
  student_name: string | null;
  university: string;
  country: string;
  status: string;
  enrollment_date: string | null;
  created_at: string;
  updated_at: string;
};

export const ORG_STATUS_LABEL: Record<OrgStatus, string> = { pending: "Pending", active: "Active", suspended: "Suspended", rejected: "Rejected" };

// The shared `.status` pill: green by default, amber for pending, red for suspended/rejected. The label is always shown as text,
// so colour is never the only signal.
export function statusClass(status: string): string {
  if (status === "pending") return "status pending";
  if (status === "suspended" || status === "rejected") return "status error";
  return "status";
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// AC11: the detail page renders only for a real id, so a crafted path segment never becomes part of an API URL.
export function isUuid(value: string): boolean {
  return UUID.test(value);
}

export function orgUrl(id: string, sub?: "students" | "applications"): string {
  return `${ORGS_URL}/${encodeURIComponent(id)}${sub ? `/${sub}` : ""}`;
}

export const NETWORK_ERROR = "Network error. Check your connection and try again.";

// A failed response's message, worded by the shared detailMessage (a body that is not JSON gets the fallback).
export async function failureText(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return detailMessage(body?.detail, fallback);
}

// One page from a list endpoint. Never throws: a failed response gives the server's message, a 200 that is not a page gives
// `fallback`, and a dropped network gives NETWORK_ERROR.
export async function fetchPage<T>(url: string, fallback: string): Promise<{ ok: true; page: Page<T> } | { ok: false; error: string }> {
  try {
    const res = await fetch(url);
    if (!res.ok) return { ok: false, error: await failureText(res, fallback) };
    const body = await res.json().catch(() => null);
    return isPage<T>(body) ? { ok: true, page: body } : { ok: false, error: fallback };
  } catch {
    return { ok: false, error: NETWORK_ERROR };
  }
}
