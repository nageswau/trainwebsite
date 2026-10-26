// nehn-041 (DEC-SCOPE-291 S1-S10): the unified Student search -- its filters (read from the page's address), the API address and the
// result shape. The API scopes every kind to what the caller already sees, so the page never filters results itself.

export const STUDENT_SEARCH_MIN = 3;
export const STUDENT_SEARCH_MAX = 100;

export const STUDENT_KINDS = [
  { value: "it_student", label: "IT students" },
  { value: "overseas_student", label: "Overseas students" },
  { value: "agency_student", label: "Agency students (no login)" },
  { value: "school_student", label: "School students" },
] as const;
export type StudentKind = (typeof STUDENT_KINDS)[number]["value"];

/** The kinds each admin portal's caller can see (S1) -- only these are offered in the Type filter. */
export const ROLE_KINDS: Record<string, StudentKind[]> = {
  super_admin: ["it_student", "overseas_student", "agency_student", "school_student"],
  it_admin: ["it_student"],
  overseas_admin: ["overseas_student", "agency_student"],
};

export type StudentHit = { id: string; code: string | null; label: string | null; detail: string; href: string | null };
export type StudentGroup = { items: StudentHit[]; more: boolean };
export type StudentSearchResult = { q: string; groups: Partial<Record<StudentKind, StudentGroup>> };
export type StudentSearchFilters = { q: string; type: StudentKind | ""; program: string };

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The filters from the page's search params, trimmed. A repeated param, an unknown type or a malformed program only comes from a
 *  hand-edited address and is dropped. */
export function studentSearchFilters(search: Record<string, string | string[] | undefined>): StudentSearchFilters {
  const one = (key: string) => (typeof search[key] === "string" ? (search[key] as string).trim() : "");
  const type = one("type");
  return {
    q: one("q"),
    type: STUDENT_KINDS.some((k) => k.value === type) ? (type as StudentKind) : "",
    program: UUID_SHAPE.test(one("program")) ? one("program") : "",
  };
}

/** What the API would refuse, in words; "" when the search can be sent. An empty search is not an error (the page just shows the form). */
export function studentSearchError(filters: StudentSearchFilters): string {
  if (filters.q && filters.q.length < STUDENT_SEARCH_MIN) return `Type at least ${STUDENT_SEARCH_MIN} characters.`;
  if (filters.q.length > STUDENT_SEARCH_MAX) return `Use at most ${STUDENT_SEARCH_MAX} characters.`;
  return "";
}

export function studentSearchUrl(filters: StudentSearchFilters): string {
  const params = new URLSearchParams({ q: filters.q });
  if (filters.type) params.set("type", filters.type);
  if (filters.program) params.set("program", filters.program);
  return `/api/v1/search/students?${params}`;
}
