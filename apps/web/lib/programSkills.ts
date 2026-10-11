// rec-036 (DEC-SCOPE-176 CI1): a program's skill tags -- types and endpoints. The API decides who may edit and every rule (active Skills
// Master skills, at most 30); `skill-options` is the IT admin's picker (it_admin cannot read the Skills Master itself, Q-28).
import type { LookupPage } from "@/lib/lookups";

export type ProgramSkill = { id: string; name: string; active: boolean; category: string };
export type ProgramSkillsSaved = { items: ProgramSkill[]; candidates_updated: number };

export const programSkillsUrl = (programId: string) => `/api/v1/admin/programs/${encodeURIComponent(programId)}/skills`;

export async function programSkillOptions(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = q ? `?${new URLSearchParams({ q })}` : "";
  const response = await fetch(`/api/v1/admin/programs/skill-options${query}`, { signal });
  if (!response.ok) throw new Error(`Skill search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; name: string; category: string }[] };
  return { items: page.items.map((s) => ({ id: s.id, label: s.name, detail: s.category })), truncated: page.items.length >= 20 };
}

export const isProgramSkills = (body: unknown): body is { items: ProgramSkill[] } =>
  typeof body === "object" && body !== null && Array.isArray((body as { items?: unknown }).items);
