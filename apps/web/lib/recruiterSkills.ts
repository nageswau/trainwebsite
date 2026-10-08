// rec-006 (DEC-SCOPE-118): the recruiter Skills Master -- types, endpoints and the related-skill picker's data source. (lib/skills.ts is
// the unrelated School skills module.) Labels are display only -- the API decides who may read and write.
import type { Page } from "@/lib/apiErrors";
import type { LookupPage } from "@/lib/lookups";
import { getPage } from "@/lib/telecallerCatalogue";

export type SkillRef = { id: string; name: string; active: boolean };
export type SkillCategory = SkillRef & { sort_order: number };
export type Skill = SkillRef & { category: SkillRef; tags: SkillRef[]; aliases: { id: string; alias: string }[]; related: SkillRef[] };
export type SkillsState = { q: string; category: string; offset: number };

export const SKILLS_URL = "/api/v1/recruiter/skills";
export const SKILL_CATEGORIES_URL = "/api/v1/recruiter/skill-categories";
export const SKILLS_PAGE_SIZE = 50;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A hand-edited `?category=` that is not an id is ignored rather than sent to the API as a 422 (QA-05). */
export function skillsQuery({ q, category, offset }: SkillsState, limit: number): string {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) query.set("q", q);
  if (UUID.test(category)) query.set("category_id", category);
  return query.toString();
}

/** Every category, page by page (the API caps a page at 100), for the filter and the pickers (QA-02). */
export async function allCategories(signal: AbortSignal): Promise<SkillCategory[]> {
  const items: SkillCategory[] = [];
  let page: Page<SkillCategory>;
  do {
    page = await getPage<SkillCategory>(`${SKILL_CATEGORIES_URL}?limit=100&offset=${items.length}`, signal);
    items.push(...page.items);
  } while (page.items.length > 0 && items.length < page.total);
  return items;
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
