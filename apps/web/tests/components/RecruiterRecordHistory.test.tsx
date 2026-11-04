import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRecordHistory from "@/components/RecruiterRecordHistory";
import type { HistoryItem } from "@/lib/recruiterHistory";

// hrc-004 (DEC-SCOPE-376 B6/B7): a job's or candidate's Change history -- old → new values, "changed (value hidden)" for compensation
// and contact fields, older rows' field names, the loading / empty / error + Retry states, and "Show older".
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Partial<HistoryItem> = {}): HistoryItem => ({
  id: "A1", action: "recruiter_requirement.update", created_at: "2026-11-04T05:30:00Z", actor: { id: "U1", full_name: "Asha Recruiter" },
  changes: { title: ["Java Dev", "Senior Java Dev"], salary_min: "changed" }, fields: ["salary_min", "title"], ...over,
});

let pages: unknown[];
let fails: boolean;
beforeEach(() => {
  pages = [{ items: [item()], total: 1, limit: 20, offset: 0 }];
  fails = false;
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fails ? res({ detail: "boom" }, 500) : res(pages.shift()))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterRecordHistory (hrc-004)", () => {
  it("AC1/AC2: shows a title's old and new value and a salary as changed, with who did it", async () => {
    render(<RecruiterRecordHistory url="/api/v1/recruiter/requirements/R1/history" />);
    const list = await screen.findByRole("list", { name: "Change history" });
    const [row] = within(list).getAllByRole("listitem", { name: /Details edited/ });
    expect(row.textContent).toContain("Asha Recruiter");
    expect(within(row).getByText("Title: Java Dev → Senior Java Dev")).toBeTruthy();
    expect(within(row).getByText("Salary min: changed (value hidden)")).toBeTruthy();
    expect(row.textContent).not.toContain("salary_min");
    expect(fetch).toHaveBeenCalledWith("/api/v1/recruiter/requirements/R1/history?limit=20&offset=0", expect.anything());
  });

  it("shows an older row's field names when it has no values, and a system change", async () => {
    pages = [{ items: [item({ changes: null, fields: ["location", "notice_days"], actor: null, action: "candidate.update" })], total: 1, limit: 20, offset: 0 }];
    render(<RecruiterRecordHistory url="/h" />);
    const row = await screen.findByRole("listitem", { name: /Profile edited/ });
    expect(row.textContent).toContain("Changed: Location, Notice days");
    expect(row.textContent).toContain("the system");
  });

  it("QA-01/QA-02: a creation lists the fields it set, and an id field reads as its name", async () => {
    pages = [{ items: [item({ action: "candidate.create", changes: null, fields: ["name", "source_id", "job_category_id"] })], total: 1, limit: 20, offset: 0 }];
    render(<RecruiterRecordHistory url="/h" />);
    const row = await screen.findByRole("listitem", { name: /Created/ });
    expect(row.textContent).toContain("Fields set: Name, Source, Job category");
    expect(row.textContent).not.toContain("Changed:");
  });

  it("says so when nothing has changed yet", async () => {
    pages = [{ items: [], total: 0, limit: 20, offset: 0 }];
    render(<RecruiterRecordHistory url="/h" />);
    expect(await screen.findByText("No changes recorded yet.")).toBeTruthy();
  });

  it("shows the loading state, then an error with Retry that reloads", async () => {
    fails = true;
    render(<RecruiterRecordHistory url="/h" />);
    expect(screen.getByRole("status").textContent).toContain("Loading history");
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the history.");
    fails = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Change history" })).toBeTruthy();
  });

  it("loads older changes onto the end of the list", async () => {
    pages = [
      { items: [item({ id: "A2" })], total: 2, limit: 20, offset: 0 },
      { items: [item({ id: "A1", action: "recruiter_requirement.status", changes: { status: ["sourcing", "on_hold"] } })], total: 2, limit: 20, offset: 1 },
    ];
    render(<RecruiterRecordHistory url="/h" />);
    fireEvent.click(await screen.findByRole("button", { name: "Show older changes" }));
    const status = await screen.findByRole("listitem", { name: /Status changed/ });
    expect(within(status).getByText("Status: Sourcing → On hold")).toBeTruthy();
    expect(fetch).toHaveBeenLastCalledWith("/h?limit=20&offset=1", expect.anything());
    expect(screen.queryByRole("button", { name: "Show older changes" })).toBeNull();
  });
});
