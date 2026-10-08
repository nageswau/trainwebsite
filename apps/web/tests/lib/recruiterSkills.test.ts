import { afterEach, describe, expect, it, vi } from "vitest";

import { categoryLabel, skillSearch, SKILLS_URL, skillsQuery } from "@/lib/recruiterSkills";

afterEach(() => vi.unstubAllGlobals());

describe("rec-006 recruiter skills lib", () => {
  it("builds the list query from the URL state, leaving out empty values", () => {
    expect(skillsQuery({ q: "", category: "", offset: 0 }, 50)).toBe("limit=50&offset=0");
    expect(skillsQuery({ q: "react js", category: "c1", offset: 50 }, 50)).toBe("limit=50&offset=50&q=react+js&category_id=c1");
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
