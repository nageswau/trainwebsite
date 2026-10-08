import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateSkills from "@/components/RecruiterCandidateSkills";
import type { CandidateSkill } from "@/lib/recruiterCandidateSkills";
import { candidateSkill } from "@/tests/helpers/recruiterCandidateSkills";

// rec-011 (spec §6; AC1-AC4): the candidate's Skills card -- the table, Add from the Skills Master, the server's 409/422 sentence,
// Edit, the status moves with who/when, Remove with a confirm, read only without can_edit, and the load error with Retry.
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const BASE = "/api/v1/recruiter/candidates/C1/skills";

let items: CandidateSkill[];
let canEdit: boolean;
let writeReply: () => Response;
let listFails: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [
    candidateSkill(),
    candidateSkill({ id: "S2", skill: { id: "K-py", name: "Python", active: true }, level: "beginner", experience_months: null, last_used_year: null,
      source: "certification", status: "verified", verified_by: { id: "m1", full_name: "Mona Manager" }, verified_at: "2026-10-08T06:00:00Z" }),
  ];
  canEdit = true;
  listFails = false;
  writeReply = () => res(candidateSkill({ id: "S3", skill: { id: "K-react", name: "React", active: true } }), 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(writeReply());
    if (url === BASE) return Promise.resolve(listFails ? res({ detail: "boom" }, 500) : res({ items, can_edit: canEdit }));
    if (url.startsWith("/api/v1/recruiter/skills?")) {
      return Promise.resolve(res({ items: [{ id: "K-react", name: "React", active: true, category: { id: "G2", name: "Frontend", active: true }, tags: [], aliases: [], related: [] }], total: 1 }));
    }
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const call = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === method).at(-1)!;
  const body = (call[1] as RequestInit).body;
  return { url: String(call[0]), body: body ? JSON.parse(String(body)) : null };
};

async function openAdd() {
  fireEvent.click(await screen.findByRole("button", { name: "Add skill" }));
  const form = screen.getByRole("form", { name: "Add skill" });
  const picker = within(form).getByRole("combobox", { name: /Skill/ });
  fireEvent.focus(picker);
  fireEvent.change(picker, { target: { value: "rea" } });
  fireEvent.click(await within(form).findByRole("option", { name: /React/ }));
  return form;
}

describe("RecruiterCandidateSkills (rec-011)", () => {
  it("lists each skill with level, experience, last used, source and status with who verified", async () => {
    render(<RecruiterCandidateSkills candidateId="C1" />);
    const table = await screen.findByRole("table", { name: "Skills" });
    const [java, python] = within(table).getAllByRole("row").slice(1);
    expect(java.textContent).toContain("Java");
    expect(java.textContent).toContain("Programming");
    expect(java.textContent).toContain("Advanced");
    expect(java.textContent).toContain("3 yr");
    expect(java.textContent).toContain("2026");
    expect(java.textContent).toContain("Resume");
    expect(java.textContent).toContain("Claimed");
    expect(python.textContent).toContain("Verified");
    expect(python.textContent).toContain("Mona Manager");
    expect(python.textContent).toContain("Certification");
  });

  it("adds a skill picked from the Skills Master and reloads", async () => {
    render(<RecruiterCandidateSkills candidateId="C1" />);
    const form = await openAdd();
    fireEvent.change(within(form).getByLabelText(/Level/), { target: { value: "expert" } });
    fireEvent.change(within(form).getByLabelText(/Experience/), { target: { value: "24" } });
    fireEvent.change(within(form).getByLabelText(/Source/), { target: { value: "course_completed" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Added React."));
    expect(sent("POST")).toEqual({ url: BASE, body: { skill: "React", level: "expert", experience_months: 24, last_used_year: null, source: "course_completed" } });
    expect(fetchMock.mock.calls.filter(([url, init]) => url === BASE && !(init as RequestInit | undefined)?.method)).toHaveLength(2);
  });

  it("asks for a skill and a level before sending, and shows the server's sentence on a 409", async () => {
    render(<RecruiterCandidateSkills candidateId="C1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add skill" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Add skill" })).getByRole("button", { name: "Add" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a skill from the list.");
    cleanup();
    writeReply = () => res({ detail: "React is already on this candidate's skills" }, 409);
    render(<RecruiterCandidateSkills candidateId="C1" />);
    const form = await openAdd();
    fireEvent.change(within(form).getByLabelText(/Level/), { target: { value: "advanced" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add" }));
    expect((await screen.findByRole("alert")).textContent).toBe("React is already on this candidate's skills");
    expect(screen.getByRole("form", { name: "Add skill" })).toBeInTheDocument(); // the entry is kept
  });

  it("edits a row without sending the skill", async () => {
    writeReply = () => res(candidateSkill({ level: "expert" }));
    render(<RecruiterCandidateSkills candidateId="C1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Java" }));
    const form = screen.getByRole("form", { name: "Edit Java" });
    fireEvent.change(within(form).getByLabelText(/Level/), { target: { value: "expert" } });
    fireEvent.change(within(form).getByLabelText(/Last used/), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Saved Java."));
    expect(sent("PATCH")).toEqual({ url: `${BASE}/S1`, body: { level: "expert", experience_months: 36, last_used_year: null, source: "resume" } });
  });

  it("changes the status and removes after a confirm", async () => {
    writeReply = () => res(candidateSkill({ status: "verified" }));
    render(<RecruiterCandidateSkills candidateId="C1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark verified: Java" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Java marked verified."));
    expect(sent("POST")).toEqual({ url: `${BASE}/S1/status`, body: { status: "verified" } });
    writeReply = () => res(null, 204);
    fireEvent.click(screen.getByRole("button", { name: "Remove Java" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Removed Java."));
    expect(sent("DELETE").url).toBe(`${BASE}/S1`);
  });

  it("is read only without can_edit", async () => {
    canEdit = false;
    render(<RecruiterCandidateSkills candidateId="C1" />);
    await screen.findByRole("table", { name: "Skills" });
    expect(screen.queryByRole("button", { name: "Add skill" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Edit|Remove|Mark/ })).toBeNull();
  });

  it("shows the empty state, and a load error with Retry", async () => {
    items = [];
    render(<RecruiterCandidateSkills candidateId="C1" />);
    expect(await screen.findByText("No skills added yet.")).toBeInTheDocument();
    cleanup();
    listFails = true;
    render(<RecruiterCandidateSkills candidateId="C1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load the skills.");
    listFails = false;
    items = [candidateSkill()];
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table", { name: "Skills" })).toBeInTheDocument();
  });
});
