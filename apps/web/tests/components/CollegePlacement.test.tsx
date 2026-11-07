import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CollegePlacement from "@/components/CollegePlacement";
import RecruiterColleges from "@/components/RecruiterColleges";
import { type College, dayText, hasPlacementProfile } from "@/lib/recruiterColleges";

// pob-013 (DEC-SCOPE-410): the college placement section and the colleges search.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(handler(call));
  }));
  return calls;
}

const college: College = {
  id: "o1", code: "ORG-000001", name: "St Mary's College", org_type: "college", city: "Kochi", state: "Kerala", website: null, student_count: 1200,
  affiliation: "KTU", college_type: "engineering", courses_note: "B.Tech, MBA", relationship_stage: "Prospect", assigned_bdm_name: "Anil BDM", archived: false,
  permissions: { can_edit: true },
  profile: { drive_process: null, eligibility_rules: null, updated_at: null, updated_by_name: null },
  contacts: [{ id: "k1", name: "Ms Iyer", designation: "TPO", role: "placement_officer", phone: null, email: null, is_primary: true, office_details: null,
               preferred_contact_method: null }],
  courses: [{ id: "c1", department: "CSE", course: "B.Tech CSE" }],
  batches: [], calendar: [], interactions: [], interaction_total: 0, drives: [],
};
const body = (patch: Partial<College> = {}) => ({ college: { ...college, ...patch } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("only a college-module college or university has a placement profile", () => {
    expect(hasPlacementProfile({ org_type: "college", bdm_type: "college" })).toBe(true);
    expect(hasPlacementProfile({ org_type: "university", bdm_type: "college" })).toBe(true);
    expect(hasPlacementProfile({ org_type: "university", bdm_type: "agent" })).toBe(false);
    expect(hasPlacementProfile({ org_type: "school", bdm_type: "school" })).toBe(false);
  });

  it("reads a date as a calendar day", () => {
    expect(dayText("2027-05-31")).toBe("31 May 2027");
    expect(dayText(null)).toBe("—");
  });
});

describe("CollegePlacement", () => {
  it("loads itself, then shows empty states and the TPO contact", async () => {
    serve(() => res(body()));
    render(<CollegePlacement orgId="o1" />);
    expect(screen.getByText("Loading the placement profile…")).toBeTruthy();
    expect(await screen.findByText("No batches yet.")).toBeTruthy();
    expect(screen.getByText("No calendar entries yet.")).toBeTruthy();
    expect(screen.getByText("No TPO interactions yet.")).toBeTruthy();
    expect(screen.getByText("Ms Iyer", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText(/Relationship stage: Prospect/)).toBeTruthy();
  });

  it("offers a retry when loading fails", async () => {
    let fail = true;
    const calls = serve(() => (fail ? res({ detail: "boom" }, 500) : res(body())));
    render(<CollegePlacement orgId="o1" />);
    expect(await screen.findByText("Unable to load the placement profile.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No batches yet.")).toBeTruthy();
    expect(calls).toHaveLength(2);
  });

  it("read only: no forms and no edit buttons", () => {
    serve(() => res(body()));
    render(<CollegePlacement orgId="o1" initial={{ ...college, permissions: { can_edit: false } }} />);
    expect(screen.queryByRole("form", { name: "Add a batch" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(screen.getByText(/Read only/)).toBeTruthy();
  });

  it("adds a batch with numbers as numbers and re-renders from the response", async () => {
    const batch = { id: "b1", course_id: "c1", course: "B.Tech CSE", pass_out_year: 2027, pass_out_date: null, student_count: 120, notes: null };
    const calls = serve(() => res(body({ batches: [batch] }), 201));
    render(<CollegePlacement orgId="o1" initial={college} />);
    const form = screen.getByRole("form", { name: "Add a batch" });
    fireEvent.change(within(form).getByLabelText("Pass-out year"), { target: { value: "2027" } });
    fireEvent.change(within(form).getByLabelText("Course (optional)"), { target: { value: "c1" } });
    fireEvent.change(within(form).getByLabelText("Students (optional)"), { target: { value: "120" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Batch added.")).toBeTruthy();
    expect(calls[0].url).toBe("/api/v1/recruiter/colleges/o1/batches");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ pass_out_year: 2027, course_id: "c1", pass_out_date: null, student_count: 120, notes: null });
    expect(screen.getByRole("region", { name: "Graduating batches" })).toBeTruthy();
  });

  it("shows the API's refusal at the form that was used and keeps the entry", async () => {
    serve(() => res({ detail: [{ msg: "Value error, Pass-out year must be a year from 2000 to 2100" }] }, 422));
    render(<CollegePlacement orgId="o1" initial={college} />);
    const form = screen.getByRole("form", { name: "Add a batch" });
    const year = within(form).getByLabelText("Pass-out year") as HTMLInputElement;
    fireEvent.change(year, { target: { value: "1999" } });
    fireEvent.submit(form);
    expect(await within(form).findByRole("alert")).toHaveProperty("textContent", "Pass-out year must be a year from 2000 to 2100");
    expect(year.value).toBe("1999");
  });

  it("logs a TPO interaction with an ISO time and the chosen contact", async () => {
    const calls = serve(() => res(body(), 201));
    render(<CollegePlacement orgId="o1" initial={college} />);
    const form = screen.getByRole("form", { name: "Log a TPO interaction" });
    fireEvent.change(within(form).getByLabelText("When"), { target: { value: "2026-11-04T10:30" } });
    fireEvent.change(within(form).getByLabelText("With (optional)"), { target: { value: "k1" } });
    fireEvent.change(within(form).getByLabelText("Summary"), { target: { value: "Agreed the drive window" } });
    fireEvent.submit(form);
    await waitFor(() => expect(calls).toHaveLength(1));
    const sent = JSON.parse(String(calls[0].init?.body));
    expect(sent).toMatchObject({ channel: "meeting", contact_id: "k1", summary: "Agreed the drive window", next_step: null });
    expect(sent.occurred_at).toBe(new Date("2026-11-04T10:30").toISOString());
  });

  it("on the BDM page, sends its notice to the page's live region and renders none of its own", async () => {
    serve(() => res(body(), 201));
    const notify = vi.fn();
    render(<CollegePlacement orgId="o1" initial={college} onNotice={notify} />);
    expect(screen.queryByRole("status")).toBeNull();
    const form = screen.getByRole("form", { name: "Add a calendar entry" });
    fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "PPT" } });
    fireEvent.change(within(form).getByLabelText("Start date"), { target: { value: "2026-12-01" } });
    fireEvent.submit(form);
    await waitFor(() => expect(notify).toHaveBeenCalledWith("Calendar entry added."));
  });

  it("asks before removing a course", async () => {
    const calls = serve(() => res(body({ courses: [] })));
    render(<CollegePlacement orgId="o1" initial={college} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove B.Tech CSE" }));
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByText("Course removed.")).toBeTruthy();
    expect(calls[0]).toMatchObject({ url: "/api/v1/recruiter/colleges/o1/courses/c1", init: { method: "DELETE" } });
  });

  it("edits the TPO office details and preferred method", async () => {
    const saved = { ...college.contacts[0], office_details: "Block A", preferred_contact_method: "whatsapp" };
    const calls = serve(() => res(body({ contacts: [saved] })));
    render(<CollegePlacement orgId="o1" initial={college} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit TPO details for Ms Iyer" }));
    const form = screen.getByRole("form", { name: "TPO details for Ms Iyer" });
    fireEvent.change(within(form).getByLabelText("Office details"), { target: { value: "Block A" } });
    fireEvent.change(within(form).getByLabelText("Preferred contact method"), { target: { value: "whatsapp" } });
    fireEvent.submit(form);
    expect(await screen.findByText("TPO details saved.")).toBeTruthy();
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ office_details: "Block A", preferred_contact_method: "whatsapp" });
    expect(screen.getByText("Preferred contact: WhatsApp")).toBeTruthy();
  });
});

describe("RecruiterColleges", () => {
  const row = { id: "o1", code: "ORG-000001", name: "St Mary's College", org_type: "college", city: "Kochi", state: "Kerala", assigned_bdm_name: "Anil",
                course_count: 2, next_pass_out_year: 2027, archived: false };

  it("searches by course and year on submit and links each college", async () => {
    const calls = serve(() => res({ items: [row], total: 1, limit: 25, offset: 0 }));
    render(<RecruiterColleges />);
    expect(await screen.findByRole("link", { name: "St Mary's College" })).toHaveProperty("href", expect.stringContaining("/recruiter/colleges/o1"));
    fireEvent.change(screen.getByLabelText("Course"), { target: { value: "B.Tech" } });
    fireEvent.change(screen.getByLabelText("Pass-out year"), { target: { value: "2027" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(calls).toHaveLength(2));
    const query = new URL(calls[1].url, "http://x").searchParams;
    expect(query.get("course")).toBe("B.Tech");
    expect(query.get("pass_out_year")).toBe("2027");
  });

  it("says when nothing matches", async () => {
    serve(() => res({ items: [], total: 0, limit: 25, offset: 0 }));
    render(<RecruiterColleges />);
    expect(await screen.findByText(/No colleges yet/)).toBeTruthy();
  });
});
