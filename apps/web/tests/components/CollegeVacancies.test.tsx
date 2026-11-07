import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CampusCalendar, { TpoWidget } from "@/components/CampusCalendar";
import CollegeVacancies from "@/components/CollegeVacancies";
import { type CampusCalendarData, monthRange, shiftMonth, type Vacancies } from "@/lib/campusPlacement";

// pob-015 (DEC-SCOPE-426): the college's vacancies section, the campus calendar and the TPO widget.
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

const outcomes = { applications: 4, students: 3, shortlisted: 2, interviewed: 1, offered: 1, joined: 1, external: 4 };
const share = {
  id: "s1", requirement: { id: "j1", code: "REQ-000001", title: "Java developer" }, shared_on: "2026-11-06", channel: "email", template: null, notes: null,
  response: "awaiting", response_note: null, responded_at: null, responded_by_name: null, shared_by_name: "Priya PO",
};
const vacancies = (patch: Partial<Vacancies> = {}): { vacancies: Vacancies } => ({ vacancies: { shares: [], share_total: 0, outcomes, can_share: true, ...patch } });
const option = { id: "j1", code: "REQ-000001", title: "Java developer", company_name: "Acme" };

function standard(call: Call, after: () => Response = () => res(vacancies({ shares: [share], share_total: 1 }), 201)) {
  if (call.url.includes("vacancy-options")) return res({ items: [option], templates: [{ id: "t1", name: "TPO intro" }] });
  if (call.url.includes("/templates")) return res({ detail: "Not for this role" }, 403); // QA-02: never asked
  if (call.init?.method) return after();
  return res(vacancies());
}

/** The picker re-mounts once its options arrive, so wait for the enabled one. */
async function vacancyReady() {
  await waitFor(() => expect((screen.getByLabelText("Vacancy") as HTMLSelectElement).disabled).toBe(false));
  return screen.getByLabelText("Vacancy");
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("turns a month into its first and last day and moves between months", () => {
    expect(monthRange("2026-02")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(monthRange("2028-02")).toEqual({ from: "2028-02-01", to: "2028-02-29" });
    expect(monthRange("2026-13")).toBeNull();
    expect(monthRange(undefined)).toBeNull();
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  });
});

describe("CollegeVacancies", () => {
  it("loads itself, shows the outcomes and the empty timeline", async () => {
    serve((call) => standard(call));
    render(<CollegeVacancies orgId="o1" />);
    expect(screen.getByText("Loading the vacancies shared…")).toBeTruthy();
    expect(await screen.findByText("No vacancies shared with this college yet.")).toBeTruthy();
    const figures = within(screen.getByRole("list", { name: "Student outcomes" }));
    expect(figures.getByText("Applications")).toBeTruthy();
    expect(screen.getByText(/4 applications by external candidates/)).toBeTruthy();
  });

  it("records a share with the chosen vacancy, channel and template, then lists it", async () => {
    const calls = serve((call) => standard(call));
    render(<CollegeVacancies orgId="o1" />);
    fireEvent.change(await vacancyReady(), { target: { value: "j1" } });
    fireEvent.change(screen.getByLabelText("Shared by"), { target: { value: "whatsapp" } });
    fireEvent.change(await screen.findByLabelText("Template (optional)"), { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Record share" }));
    expect(await screen.findByText("Vacancy share recorded.")).toBeTruthy();
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(post.url).toBe("/api/v1/recruiter/colleges/o1/vacancy-shares");
    expect(JSON.parse(String(post.init?.body))).toEqual({ requirement_id: "j1", channel: "whatsapp", shared_on: null, template_id: "t1", notes: null });
    expect(screen.getByText("REQ-000001 · Java developer")).toBeTruthy();
    expect(screen.getByText("Awaiting reply")).toBeTruthy();
  });

  it("searches again with the same text (QA-01) and takes its templates from the options, never the template library (QA-02)", async () => {
    const calls = serve((call) => standard(call));
    render(<CollegeVacancies orgId="o1" />);
    await vacancyReady();
    fireEvent.change(screen.getByLabelText("Find a vacancy"), { target: { value: "Java" } });
    fireEvent.click(screen.getByRole("button", { name: "Search vacancies" }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("vacancy-options?q=Java")).length).toBe(1));
    fireEvent.click(screen.getByRole("button", { name: "Search vacancies" }));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("vacancy-options?q=Java")).length).toBe(2));
    expect(await screen.findByLabelText("Template (optional)")).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/recruiter/templates"))).toBe(false);
  });

  it("asks for a vacancy before sending, and shows the server's refusal", async () => {
    const calls = serve((call) => standard(call, () => res({ detail: "Only open vacancies that are not internal can be shared" }, 422)));
    render(<CollegeVacancies orgId="o1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Record share" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a vacancy to share.");
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
    fireEvent.change(await vacancyReady(), { target: { value: "j1" } });
    fireEvent.click(screen.getByRole("button", { name: "Record share" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Only open vacancies that are not internal can be shared");
  });

  it("records the college's reply on a share", async () => {
    const answered = { ...share, response: "interested", response_note: "40 students", responded_by_name: "Priya PO", responded_at: "2026-11-07T05:00:00Z" };
    const calls = serve((call) => {
      if (call.init?.method === "PATCH") return res(vacancies({ shares: [answered], share_total: 1 }));
      if (call.url.endsWith("/vacancies")) return res(vacancies({ shares: [share], share_total: 1 }));
      return standard(call);
    });
    render(<CollegeVacancies orgId="o1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Record the reply for Java developer" }));
    fireEvent.change(screen.getByLabelText("Reply"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "40 students" } });
    fireEvent.click(screen.getByRole("button", { name: "Save reply" }));
    expect(await screen.findByText("Reply saved.")).toBeTruthy();
    const patch = calls.find((c) => c.init?.method === "PATCH")!;
    expect(patch.url).toBe("/api/v1/recruiter/colleges/o1/vacancy-shares/s1");
    expect(JSON.parse(String(patch.init?.body))).toEqual({ response: "interested", response_note: "40 students" });
    expect(screen.getByText("Interested")).toBeTruthy();
  });

  it("is read only without can_share and offers a retry when it cannot load", async () => {
    let fail = true;
    serve((call) => (fail ? res({ detail: "boom" }, 500) : standard(call, () => res({}, 500))));
    render(<CollegeVacancies orgId="o1" />);
    expect(await screen.findByText("Unable to load the vacancies shared with this college.")).toBeTruthy();
    fail = false;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(vacancies({ can_share: false, shares: [share], share_total: 1 })))));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("REQ-000001 · Java developer")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Share a vacancy" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Record the reply/ })).toBeNull();
  });
});

describe("CampusCalendar", () => {
  const data: CampusCalendarData = {
    from: "2026-12-01", to: "2026-12-31", truncated: false,
    items: [
      { kind: "drive", id: "d1", date: "2026-12-03", end_date: null, title: "Java dev", code: "DRV-000001", status: "planned", event_kind: null, student_count: null,
        college: { id: "o1", code: "ORG-000001", name: "St Mary's College" } },
      { kind: "batch", id: "b1", date: "2026-12-03", end_date: null, title: "2026 batch pass-out", code: null, status: null, event_kind: null, student_count: 120,
        college: { id: "o1", code: "ORG-000001", name: "St Mary's College" } },
    ],
  };

  it("groups the month's drives and batches by day and links each college", () => {
    render(<CampusCalendar data={data} month="2026-12" basePath="/recruiter/campus-calendar" collegePath={(id) => `/recruiter/colleges/${id}`} />);
    expect(screen.getByRole("heading", { name: "3 Dec 2026" })).toBeTruthy();
    expect(screen.getByText("Campus drive")).toBeTruthy();
    expect(screen.getByText("Batch pass-out")).toBeTruthy();
    expect(screen.getByText(/DRV-000001 · Planned/)).toBeTruthy();
    expect(screen.getByText(/120 students/)).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "St Mary's College" })[0].getAttribute("href")).toBe("/recruiter/colleges/o1");
    expect(screen.getByRole("link", { name: "Next month →" }).getAttribute("href")).toBe("/recruiter/campus-calendar?month=2027-01");
    expect(screen.getByRole("link", { name: "Download calendar (.ics)" }).getAttribute("href")).toBe("/api/v1/recruiter/campus-calendar.ics?from=2026-12-01&to=2026-12-31");
  });

  it("shows the empty and failed states", () => {
    render(<CampusCalendar data={{ ...data, items: [] }} month="2026-12" basePath="/b" collegePath={(id) => id} />);
    expect(screen.getByText("No campus drives, placement calendar entries or batch pass-outs this month.")).toBeTruthy();
    cleanup();
    render(<CampusCalendar data={null} month="2026-12" basePath="/b" collegePath={(id) => id} />);
    expect(screen.getByText("Unable to load the campus calendar. Please reload the page.")).toBeTruthy();
  });

  it("the TPO widget shows the figures, or a failure", () => {
    render(<TpoWidget summary={{ colleges: 7, shared_30d: 3, awaiting: 2, upcoming_30d: 5, upcoming_truncated: false, outcomes }} />);
    expect(screen.getByText("Vacancies shared (30 days)").previousSibling?.textContent).toBe("3");
    expect(screen.getByText("Students: joined").previousSibling?.textContent).toBe("1");
    cleanup();
    render(<TpoWidget summary={null} />);
    expect(screen.getByText("Unable to load the TPO summary.")).toBeTruthy();
  });
});
