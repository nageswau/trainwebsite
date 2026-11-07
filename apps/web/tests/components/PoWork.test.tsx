import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PoActivityReport from "@/components/PoActivityReport";
import PoDailyPlan from "@/components/PoDailyPlan";
import { RECRUITER_NAV } from "@/lib/navigation";
import { cellText, chosenPeriod, contactsUrl, mondayOf, type Plan, type Report } from "@/lib/recruiterPoWork";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("pob-009 helpers", () => {
  it("snaps a week to its Monday and keeps a day (AC3)", () => {
    expect(mondayOf("2026-11-08")).toBe("2026-11-02"); // Sunday -> the Monday before
    expect(mondayOf("2026-11-02")).toBe("2026-11-02");
    expect(chosenPeriod({ period: "weekly", start: "2026-11-05" }, "2026-11-07")).toEqual({ period: "weekly", start: "2026-11-02" });
    expect(chosenPeriod({ start: "2026-12-01" }, "2026-11-07")).toEqual({ period: "daily", start: "2026-11-07" }); // future -> today
    expect(chosenPeriod({ start: "nope" }, "2026-11-07")).toEqual({ period: "daily", start: "2026-11-07" });
  });

  it("writes target vs actual (AC2)", () => {
    expect(cellText({ key: "outreach", target: 40, achieved: 10, percent: 25 }, "current")).toBe("10 / 40 (25%)");
    expect(cellText({ key: "outreach", target: null, achieved: 3, percent: null }, "current")).toBe("3");
    expect(cellText({ key: "outreach", target: 5, achieved: null, percent: null }, "future")).toBe("— / 5");
  });

  it("offers the PO pages in the recruiter menu", () => {
    const hrefs = RECRUITER_NAV.map((x) => x.href);
    expect(hrefs).toEqual(expect.arrayContaining(["/recruiter/targets", "/recruiter/daily-plan", "/recruiter/activity-reports"]));
  });
});

const report: Report = {
  recruiter: { id: "u1", full_name: "Asha" }, period: "weekly", period_start: "2026-11-02", period_end: "2026-11-08", status: "draft",
  counts: { outreach: 7, responses: 1, meetings: 2, requirements: 0, vendor_registrations: 0, active_accounts: 1, placements: 0, contacts_reached: 4, response_rate: 25 },
  plan: null, note: null, submitted_at: null, kpis: [{ key: "outreach", label: "Outreach" }, { key: "responses", label: "Responses" }],
};

describe("PoActivityReport", () => {
  it("shows the figures and the contacts behind the response rate (AC1)", async () => {
    const fetchMock = respond(200, { total: 4, responses: 1, response_rate: 25, limit: 100, offset: 0, items: [
      { contact: { id: "k1", name: "Ravi" }, company: { id: "c1", name: "Acme" }, outreach: 3, replied: true },
    ] });
    render(<PoActivityReport report={report} canSubmit />);
    expect(screen.getByText("25%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show contacts reached" }));
    await waitFor(() => expect(screen.getByText("1 of 4 replied (25%)")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith(contactsUrl("weekly", "2026-11-02", undefined));
  });

  it("submits the note once and shows a refusal as its sentence", async () => {
    const fetchMock = respond(409, { detail: "This report has already been submitted" });
    render(<PoActivityReport report={report} canSubmit />);
    fireEvent.change(screen.getByLabelText("Notes for your Team Lead"), { target: { value: " Good week " } });
    fireEvent.click(screen.getByRole("button", { name: "Submit to Team Lead" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("already been submitted"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ note: "Good week" });
  });

  it("is read only for the Team Lead", () => {
    render(<PoActivityReport report={{ ...report, status: "submitted", note: "Done", submitted_at: "2026-11-07T10:00:00Z" }} canSubmit={false} recruiterId="u1" />);
    expect(screen.queryByRole("button", { name: "Submit to Team Lead" })).toBeNull();
    expect(screen.getByText("Done")).toBeTruthy();
  });
});

const plan: Plan = {
  date: "2026-11-07", editable: true,
  items: [{ id: "p1", kind: "company", done_at: null, follow_up: null, company: { id: "c1", name: "Acme" } }],
  suggested_follow_ups: [{ follow_up: { id: "f1", reason: "jd", due_at: "2026-11-07T05:00:00Z", status: "open", priority: "medium", notes: null, company: { id: "c2", name: "Beta" } } }],
  suggested_companies: [],
};

describe("PoDailyPlan", () => {
  it("adds a due follow-up and ticks an item done", async () => {
    const fetchMock = respond(201, { id: "p2" });
    render(<PoDailyPlan plan={plan} />);
    fireEvent.click(screen.getByRole("button", { name: "Plan follow-up with Beta" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/daily-plan/items");
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/recruiter/daily-plan/items/p1");
  });

  it("is read only for an earlier day", () => {
    render(<PoDailyPlan plan={{ ...plan, editable: false }} />);
    expect(screen.queryByRole("button", { name: /Add to plan|Remove/ })).toBeNull();
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
  });
});
