import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterSkillsPanel from "@/components/RecruiterSkillsPanel";

// rec-006: the Skills Master panel -- read-only for recruiters, full editing for placement managers. The list place lives in the URL.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), usePathname: () => "/recruiter/manager/skills", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 50, offset: 0 });
const C1 = "6f1c2a3b-0000-4000-8000-0000000000c1";
const programming = { id: C1, name: "Programming", active: true, sort_order: 1 };
const frontend = { id: "c2", name: "Frontend", active: true, sort_order: 3 };
const retiredCat = { id: "c9", name: "Old", active: false, sort_order: 9 };
const ref = (c: { id: string; name: string; active: boolean }) => ({ id: c.id, name: c.name, active: c.active });
const java = {
  id: "s1", name: "Java", active: true, category: ref(programming), tags: [],
  aliases: [{ id: "a1", alias: "J2EE" }, { id: "a2", alias: "Java 8" }], related: [{ id: "s2", name: "Core Java", active: true }],
};
const js = { id: "s3", name: "JavaScript", active: true, category: ref(programming), tags: [ref(frontend)], aliases: [], related: [] };
const php = { id: "s4", name: "PHP", active: false, category: ref(programming), tags: [], aliases: [], related: [] };

type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response | undefined, skills: unknown = page([java, js, php])) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    const handled = handler(call);
    if (handled) return Promise.resolve(handled);
    if (call.url.includes("/skill-categories")) return Promise.resolve(res(page([programming, frontend, retiredCat])));
    return Promise.resolve(res(skills));
  }));
  return calls;
}
const writes = (calls: Call[]) => calls.filter((c) => c.init?.method && c.init.method !== "GET");

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("RecruiterSkillsPanel (rec-006)", () => {
  it("shows a recruiter the skills with category, tags, aliases and related skills, and no editing controls", async () => {
    serve(() => undefined, page([java, js]));
    render(<RecruiterSkillsPanel canEdit={false} />);
    const row = (await screen.findByText("Java")).closest("tr")!;
    expect(within(row).getByText("J2EE, Java 8")).toBeInTheDocument();
    expect(within(row).getByText("Core Java")).toBeInTheDocument();
    expect(within(screen.getByText("JavaScript").closest("tr")!).getByText("Programming · also Frontend")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Manage/ })).toBeNull();
    expect(screen.queryByText("Create skill")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Categories" })).toBeNull();
  });

  it("shows the empty, no-match and error states with Retry", async () => {
    serve(() => undefined, page([]));
    render(<RecruiterSkillsPanel canEdit={false} />);
    expect(await screen.findByText("No skills yet.")).toBeInTheDocument();
    cleanup();
    nav.params = new URLSearchParams("q=zzz");
    serve(() => undefined, page([]));
    render(<RecruiterSkillsPanel canEdit={false} />);
    expect(await screen.findByText("No skills match your search.")).toBeInTheDocument();
    cleanup();
    serve(({ url }) => (url.includes("/skills?") ? res({ detail: "x" }, 500) : undefined));
    render(<RecruiterSkillsPanel canEdit={false} />);
    expect(await screen.findByText("Unable to load skills.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("puts the search and category filter in the URL", async () => {
    const calls = serve(() => undefined);
    nav.params = new URLSearchParams(`q=java&category=${C1}`);
    render(<RecruiterSkillsPanel canEdit={false} />);
    await screen.findByText("Java");
    expect(calls.some((c) => c.url.includes(`/skills?limit=50&offset=0&q=java&category_id=${C1}`))).toBe(true);
    const search = screen.getByLabelText("Search skills or aliases");
    fireEvent.change(search, { target: { value: "react" } });
    fireEvent.submit(search.closest("form")!);
    expect(nav.push).toHaveBeenCalledWith(`/recruiter/manager/skills?q=react&category=${C1}`, { scroll: false });
  });

  it("lets a manager create a category and see the inactive one", async () => {
    const calls = serve(({ url, init }) => (init?.method === "POST" && url.endsWith("/skill-categories") ? res({ id: "c5", name: "Testing", active: true, sort_order: 6 }, 201) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    const categories = await screen.findByRole("region", { name: "Categories" });
    expect(within(categories).getByText("Old")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Category name (required)"), { target: { value: "Testing" } });
    fireEvent.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByText("Added category Testing.")).toBeInTheDocument();
    expect(JSON.parse(String(writes(calls)[0].init!.body))).toEqual({ name: "Testing" });
  });

  it("creates a skill with a primary category and other categories, offering only active ones and never the primary as a tag", async () => {
    const calls = serve(({ url, init }) => (init?.method === "POST" && url.endsWith("/skills") ? res({ ...js, id: "s9", name: "TypeScript" }, 201) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    await screen.findByText("Java");
    const primary = screen.getByLabelText("Category (required)");
    expect(within(primary).queryByText("Old")).toBeNull();
    fireEvent.change(primary, { target: { value: C1 } });
    const others = screen.getByRole("group", { name: "Other categories" });
    expect(within(others).queryByLabelText("Programming")).toBeNull();
    fireEvent.click(within(others).getByLabelText("Frontend"));
    fireEvent.change(screen.getByLabelText("Skill name (required)"), { target: { value: "TypeScript" } });
    fireEvent.click(screen.getByRole("button", { name: "Create skill" }));
    expect(await screen.findByText("Created TypeScript.")).toBeInTheDocument();
    expect(JSON.parse(String(writes(calls)[0].init!.body))).toEqual({ name: "TypeScript", category_id: C1, tag_category_ids: ["c2"] });
  });

  it("shows the server's duplicate message when a skill name is taken", async () => {
    serve(({ init }) => (init?.method === "POST" ? res({ detail: "A skill named “Java” already exists" }, 409) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    await screen.findByText("Java");
    fireEvent.change(screen.getByLabelText("Category (required)"), { target: { value: C1 } });
    fireEvent.change(screen.getByLabelText("Skill name (required)"), { target: { value: "java" } });
    fireEvent.click(screen.getByRole("button", { name: "Create skill" }));
    expect(await screen.findByText("A skill named “Java” already exists")).toBeInTheDocument();
  });

  it("opens a skill to add and remove aliases", async () => {
    const withAlias = { ...java, aliases: [...java.aliases, { id: "a3", alias: "Java 23" }] };
    const calls = serve(({ url, init }) => {
      if (init?.method === "POST" && url.endsWith("/skills/s1/aliases")) return res(withAlias, 201);
      if (init?.method === "DELETE") return res(null, 204);
      return undefined;
    });
    render(<RecruiterSkillsPanel canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage Java" }));
    const detail = screen.getByRole("region", { name: "Java" });
    fireEvent.change(within(detail).getByLabelText("New alias"), { target: { value: "Java 23" } });
    fireEvent.click(within(detail).getByRole("button", { name: "Add alias" }));
    expect(await within(detail).findByText("Added alias Java 23.")).toBeInTheDocument();
    expect(within(detail).getByRole("button", { name: "Remove alias Java 23" })).toBeInTheDocument();
    fireEvent.click(within(detail).getByRole("button", { name: "Remove alias J2EE" }));
    await waitFor(() => expect(writes(calls).some((c) => c.init!.method === "DELETE" && c.url.endsWith("/skills/s1/aliases/a1"))).toBe(true));
  });

  it("shows the conflict when an alias is another skill's name", async () => {
    serve(({ init }) => (init?.method === "POST" ? res({ detail: "“Core Java” is already a skill name" }, 409) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage Java" }));
    const detail = screen.getByRole("region", { name: "Java" });
    fireEvent.change(within(detail).getByLabelText("New alias"), { target: { value: "Core Java" } });
    fireEvent.click(within(detail).getByRole("button", { name: "Add alias" }));
    expect(await within(detail).findByText("“Core Java” is already a skill name")).toBeInTheDocument();
  });

  it("saves a rename with tags and deactivates after a confirm", async () => {
    const calls = serve(({ init }) => (init?.method === "PATCH" ? res(js) : undefined));
    render(<RecruiterSkillsPanel canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage JavaScript" }));
    const detail = screen.getByRole("region", { name: "JavaScript" });
    expect(within(within(detail).getByRole("group", { name: "Other categories" })).getByLabelText("Frontend")).toBeChecked();
    fireEvent.change(within(detail).getByLabelText("Skill name (required)"), { target: { value: "JavaScript ES" } });
    fireEvent.click(within(detail).getByRole("button", { name: "Save skill" }));
    await waitFor(() => expect(writes(calls).length).toBe(1));
    expect(JSON.parse(String(writes(calls)[0].init!.body))).toEqual({ name: "JavaScript ES", category_id: C1, tag_category_ids: ["c2"] });
    fireEvent.click(within(detail).getByRole("button", { name: "Deactivate JavaScript" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(writes(calls).length).toBe(2));
    expect(JSON.parse(String(writes(calls)[1].init!.body))).toEqual({ active: false });
  });

  it("closes the detail with Close", async () => {
    serve(() => undefined);
    render(<RecruiterSkillsPanel canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Manage Java" }));
    fireEvent.click(screen.getByRole("button", { name: "Close Java" }));
    expect(screen.queryByRole("region", { name: "Java" })).toBeNull();
  });
});
