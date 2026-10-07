import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmDailyReport from "@/components/BdmDailyReport";
import type { DailyReport } from "@/lib/bdmDailyReports";

const DAY = "2026-10-06";
const counts = [
  { key: "calls_made", label: "Calls made", definition: "Outgoing calls you logged that day.", tracked: true, count: 4 },
  { key: "new_agents", label: "New agents", definition: "Not tracked yet: agent onboarding links arrive later.", tracked: false, count: null },
];
const report = (over: Partial<DailyReport> = {}): DailyReport => ({
  report_date: DAY, bdm: { id: "b1", full_name: "Asha" }, bdm_type: "agent", status: "draft", submitted_at: null, note: null, counts,
  can_submit: true, submit_window_days: 7, manager_comment: null, ...over,
});
const submitted = (over: Partial<DailyReport> = {}) =>
  report({ status: "submitted", submitted_at: "2026-10-06T13:00:00Z", note: "Met two agents", can_submit: false, ...over });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("bdm-015 daily report", () => {
  it("shows each count, and an untracked one as Not tracked with its reason (never 0)", () => {
    render(<BdmDailyReport initial={report()} mode="bdm" />);
    expect(document.querySelectorAll('dl[aria-label="Day counts"] .kpi-tile')).toHaveLength(2);
    expect(screen.getByText("Calls made").closest("div")!.textContent).toContain("4");
    const untracked = screen.getByText("New agents").closest("div")!;
    expect(untracked.textContent).toContain("Not tracked");
    expect(untracked.textContent).not.toContain("0");
    expect(screen.getByText("Not tracked yet: agent onboarding links arrive later.")).toBeTruthy();
  });

  it("submits the note after the confirm and becomes read-only", async () => {
    const fetchMock = vi.fn(async () => res(submitted(), 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmDailyReport initial={report()} mode="bdm" />);
    fireEvent.change(screen.getByLabelText("End-of-day note (optional)"), { target: { value: "Met two agents" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    expect(fetchMock).not.toHaveBeenCalled(); // the confirm comes first
    fireEvent.click(screen.getByRole("button", { name: "Yes, submit" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Report submitted. This day's activities are now locked."));
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/bdm/daily-reports/${DAY}/submit`, expect.objectContaining({ method: "POST", body: JSON.stringify({ note: "Met two agents" }) }));
    expect(screen.queryByRole("button", { name: "Submit report" })).toBeNull();
    expect(screen.getByText("Met two agents")).toBeTruthy();
    expect(screen.getByText(/Submitted/)).toBeTruthy();
  });

  it("an empty note is sent as null and Cancel keeps the draft", async () => {
    const fetchMock = vi.fn(async () => res(submitted({ note: null }), 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmDailyReport initial={report()} mode="bdm" />);
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Submit report" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, submit" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body).toBe(JSON.stringify({ note: null }));
  });

  it("an already-submitted day (409) is re-read and shown as submitted", async () => {
    const fetchMock = vi.fn(async (url: string) => (url.endsWith("/submit") ? res({ detail: "This day's report has already been submitted" }, 409) : res(submitted())));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmDailyReport initial={report()} mode="bdm" />);
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, submit" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This day's report has already been submitted"));
    await waitFor(() => expect(screen.getByText("Met two agents")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/bdm/daily-reports/${DAY}`);
  });

  it("a failed submit keeps the note and says why", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    render(<BdmDailyReport initial={report()} mode="bdm" />);
    fireEvent.change(screen.getByLabelText("End-of-day note (optional)"), { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, submit" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("did not complete"));
    expect((screen.getByLabelText("End-of-day note (optional)") as HTMLTextAreaElement).value).toBe("Keep me");
  });

  it("a day outside the window is a read-only preview", () => {
    render(<BdmDailyReport initial={report({ can_submit: false })} mode="bdm" />);
    expect(screen.queryByRole("button", { name: "Submit report" })).toBeNull();
    expect(screen.getByText("Reports can be submitted up to 7 days back. These counts are a live preview.")).toBeTruthy();
  });

  it("the manager comments on a submitted report and sees the comment", async () => {
    const commented = submitted({ manager_comment: { text: "Good work", by: { id: "m1", full_name: "Meera" }, at: "2026-10-07T05:00:00Z" } });
    const fetchMock = vi.fn(async () => res(commented));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmDailyReport initial={submitted()} mode="manager" />);
    expect(screen.queryByRole("button", { name: "Submit report" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "Good work" } });
    fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Comment saved."));
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/bdm/manager/daily-reports/b1/${DAY}/comment`, expect.objectContaining({ method: "PUT" }));
    const shown = screen.getByRole("region", { name: "Submitted report" });
    expect(shown.textContent).toContain("Good work");
    expect(shown.textContent).toContain("Meera");
  });

  it("the manager sees a draft as not submitted, with no comment form", () => {
    render(<BdmDailyReport initial={report()} mode="manager" />);
    expect(screen.getByText("Not submitted yet. These counts are a live preview.")).toBeTruthy();
    expect(screen.queryByLabelText("Your comment")).toBeNull();
  });
});
