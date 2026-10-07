// ENH-031 (DEC-SCOPE-039): the client side of the role-scoped read-only lookups (GET /api/v1/lookups/*) behind
// SearchableSelect. The server decides what each role may see; this only builds the request.
export type PickOption = { id: string; label: string; detail?: string | null };
export type LookupPage = { items: PickOption[]; truncated: boolean };
export type LookupName = "overseas-students" | "overseas-applications" | "overseas-counselors" | "it-job-applications" | "schools" | "school-students";

export function optionText(option: PickOption): string {
  return option.detail ? `${option.label} — ${option.detail}` : option.label;
}

export function lookupSearch(name: LookupName, params: Record<string, string | undefined> = {}) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20" });
    if (q) query.set("q", q);
    for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
    const response = await fetch(`/api/v1/lookups/${name}?${query}`, { signal });
    if (!response.ok) throw new Error(`Lookup failed (${response.status})`);
    return (await response.json()) as LookupPage;
  };
}
