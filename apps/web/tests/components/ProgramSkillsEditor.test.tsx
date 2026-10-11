import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProgramSkillsEditor from "@/components/ProgramSkillsEditor";

// rec-036 (CI1): an IT admin tags a program with Skills Master skills -- load, add from the admin lookup, remove, Save (PUT the full
// set), the server's sentence on a refusal, how many candidates were updated, and the load error with Retry.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const URL_ = "/api/v1/admin/programs/P1/skills";

let fetchMock: ReturnType<typeof vi.fn>;
let loadFails: boolean;
let putReply: () => Response;
beforeEach(() => {
  loadFails = false;
  putReply = () => res({ items: [{ id: "K-py", name: "Python", active: true, category: "Programming" }, { id: "K-dj", name: "Django", active: true, category: "Frameworks" }], candidates_updated: 3 });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PUT") return Promise.resolve(putReply());
    if (url === URL_) return Promise.resolve(loadFails ? res({ detail: "boom" }, 500) : res({ items: [{ id: "K-py", name: "Python", active: true, category: "Programming" }] }));
    if (url.startsWith("/api/v1/admin/programs/skill-options")) return Promise.resolve(res({ items: [{ id: "K-dj", name: "Django", category: "Frameworks" }] }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function addDjango() {
  const picker = await screen.findByRole("combobox", { name: /Add a skill/ });
  fireEvent.focus(picker);
  fireEvent.change(picker, { target: { value: "dj" } });
  fireEvent.click(await screen.findByRole("option", { name: /Django/ }));
}

describe("ProgramSkillsEditor (rec-036)", () => {
  it("lists the program's current skills", async () => {
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    const list = await screen.findByRole("list", { name: "Skills taught" });
    expect(within(list).getByText("Python")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Skills taught in Python Full Stack" })).toBeTruthy();
  });

  it("adds a skill, removes one and saves the full set, then says how many candidates were updated", async () => {
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    await addDjango();
    const list = screen.getByRole("list", { name: "Skills taught" });
    expect(within(list).getByText("Django")).toBeTruthy();
    fireEvent.click(within(list).getByRole("button", { name: "Remove Python" }));
    expect(within(list).queryByText("Python")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save skills" }));
    await screen.findByText(/Skills saved\. 3 candidates were updated\./);
    const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT")!;
    expect(put[0]).toBe(URL_);
    expect(JSON.parse(String((put[1] as RequestInit).body))).toEqual({ skill_ids: ["K-dj"] });
  });

  it("does not add a skill twice", async () => {
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    await addDjango();
    await addDjango();
    expect(within(screen.getByRole("list", { name: "Skills taught" })).getAllByText("Django")).toHaveLength(1);
  });

  it("shows the server's sentence when the save is refused and keeps the entry", async () => {
    putReply = () => res({ detail: "Pick active skills from the Skills Master" }, 422);
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    await addDjango();
    fireEvent.click(screen.getByRole("button", { name: "Save skills" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Pick active skills from the Skills Master");
    expect(within(screen.getByRole("list", { name: "Skills taught" })).getByText("Django")).toBeTruthy();
  });

  it("shows an empty state, and a load error with Retry", async () => {
    loadFails = true;
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load");
    loadFails = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("list", { name: "Skills taught" });
    fireEvent.click(screen.getByRole("button", { name: "Remove Python" }));
    expect(screen.getByText("No skills yet. Add the skills this program teaches.")).toBeTruthy();
  });

  it("Close calls onClose", async () => {
    const onClose = vi.fn();
    render(<ProgramSkillsEditor programId="P1" programTitle="Python Full Stack" onClose={onClose} />);
    await screen.findByRole("list", { name: "Skills taught" });
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
