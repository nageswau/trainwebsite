import { ORGS_URL } from "@/lib/bdmOrganizations";
import type { PersonRef } from "@/lib/bdmTravel";

// bdm-017 (DEC-SCOPE-070): student leads a BDM enters against an organization (`enquiries` rows). The API decides every rule; the client
// only checks that the required fields are filled. A BDM sees whether a lead converted, never which account it became.
export type Lead = {
  id: string; name: string; email: string; phone: string | null; interest: string; status: string; bdm: PersonRef; converted: boolean; created_at: string;
};
export type DuplicateMatch = { id: string; name: string; created_at: string };
export type PossibleDuplicate = { message: string; code: "possible_duplicate"; matches: DuplicateMatch[]; total: number };

export const LEADS_PAGE = 20;
export const NOTE_MAX = 5000;
export const orgLeadsUrl = (orgId: string) => `${ORGS_URL}/${orgId}/leads`;
export const orgLeadsPageUrl = (orgId: string, offset = 0) => `${orgLeadsUrl(orgId)}?limit=${LEADS_PAGE}&offset=${offset}`;

export function isLead(data: unknown): data is Lead {
  const d = data as Partial<Lead> | null;
  return !!d && typeof d.id === "string" && typeof d.email === "string" && typeof d.converted === "boolean";
}

/** The 409 `possible_duplicate` detail (bdm-002's shape), or null for any other refusal. */
export function possibleDuplicate(detail: unknown): PossibleDuplicate | null {
  const d = detail as Partial<PossibleDuplicate> | null;
  return !!d && typeof d === "object" && d.code === "possible_duplicate" && Array.isArray(d.matches) ? (d as PossibleDuplicate) : null;
}
