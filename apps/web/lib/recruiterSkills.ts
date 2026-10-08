// rec-006 (DEC-SCOPE-118): the recruiter Skills Master -- types, endpoints and the related-skill picker's data source. (lib/skills.ts is
// the unrelated School skills module.) Labels are display only -- the API decides who may read and write.
import type { LookupPage } from "@/lib/lookups";

export type SkillRef = { id: string; name: string; active: boolean };
export type SkillCategory = SkillRef & { sort_order: number };
export type Skill = SkillRef & { category: SkillRef; tags: SkillRef[]; aliases: { id: string; alias: string }[]; related: SkillRef[] };
export type SkillsState = { q: string; category: string; offset: number };

export const SKILLS_URL = "/api/v1/recruiter/skills";
export const SKILL_CATEGORIES_URL = "/api/v1/recruiter/skill-categories";
export const SKILLS_PAGE_SIZE = 50;

export function skillsQuery({ q, category, offset }: SkillsState, limit: number): string {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) query.set("q", q);
  if (category) query.set("category_id", category);
  return query.toString();
}

const named = (ref: SkillRef) => `${ref.name}${ref.active ? "" : " (inactive)"}`;

/** "Programming · also Frontend": the primary category, then any secondary tags. */
export function categoryLabel(skill: Pick<Skill, "category" | "tags">): string {
  return skill.tags.length ? `${named(skill.category)} · also ${skill.tags.map(named).join(", ")}` : named(skill.category);
}

/** The related-skill picker searches active skills on the server (SearchableSelect server mode); the skill itself is left out. */
export function skillSearch(selfId: string) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20", active: "true" });
    if (q) query.set("q", q);
    const response = await fetch(`${SKILLS_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Skill search failed (${response.status})`);
    const page = (await response.json()) as { items: Skill[]; total: number };
    return { items: page.items.filter((s) => s.id !== selfId).map((s) => ({ id: s.id, label: s.name, detail: s.category.name })), truncated: page.total > page.items.length };
  };
}
