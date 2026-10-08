import { afterEach, describe, expect, it, vi } from "vitest";

import { allCategories, categoryLabel, SKILL_CATEGORIES_URL, skillSearch, SKILLS_URL, skillsQuery } from "@/lib/recruiterSkills";

afterEach(() => vi.unstubAllGlobals());

describe("rec-006 recruiter skills lib", () => {
  it("builds the list query from the URL state, leaving out empty values", () => {
    expect(skillsQuery({ q: "", category: "", offset: 0 }, 50)).toBe("limit=50&offset=0");
    const id = "6f1c2a3b-0000-4000-8000-000000000001";
    expect(skillsQuery({ q: "react js", category: id, offset: 50 }, 50)).toBe(`limit=50&offset=50&q=react+js&category_id=${id}`);
  });

  it("drops a hand-edited category that is not an id, instead of sending the API a 422 (QA-05)", () => {
    expect(skillsQuery({ q: "", category: "zzz", offset: 0 }, 50)).toBe("limit=50&offset=0");
  });

  it("reads every category page, not just the first 100 (QA-02)", async () => {
    const cat = (i: number) => ({ id: `c${i}`, name: `C${i}`, active: true, sort_order: i });
    const first = Array.from({ length: 100 }, (_, i) => cat(i));
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: first, total: 101, limit: 100, offset: 0 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [cat(100)], total: 101, limit: 100, offset: 100 }) });
    vi.stubGlobal("fetch", fetchMock);
    const all = await allCategories(new AbortController().signal);
    expect(all).toHaveLength(101);
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([`${SKILL_CATEGORIES_URL}?limit=100&offset=0`, `${SKILL_CATEGORIES_URL}?limit=100&offset=100`]);
  });

  it("labels a category with its tags and flags inactive ones", () => {
    const skill = { category: { id: "a", name: "Programming", active: true }, tags: [{ id: "b", name: "Frontend", active: false }] };
    expect(categoryLabel(skill)).toBe("Programming · also Frontend (inactive)");
    expect(categoryLabel({ ...skill, tags: [] })).toBe("Programming");
  });

  it("searches active skills for the related-skill picker, excluding the skill itself", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ id: "s1", name: "Java", category: { name: "Programming" } }, { id: "self", name: "Self", category: { name: "X" } }], total: 3 }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const page = await skillSearch("self")("ja", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toBe(`${SKILLS_URL}?limit=20&active=true&q=ja`);
    expect(page).toEqual({ items: [{ id: "s1", label: "Java", detail: "Programming" }], truncated: true });
  });
});
