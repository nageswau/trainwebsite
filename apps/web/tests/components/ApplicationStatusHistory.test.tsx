import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationStatusHistory from "@/components/ApplicationStatusHistory";

// ccrm-016 (DEC-SCOPE-247): an application's status history -- stage, sub-status, outcome, author, time and notes / reason. The student's
// rows arrive without author, notes or reason (H2, filtered on the server); the component shows what it is given.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const URL = "/api/v1/workflows/overseas/applications/a1/status";
const json = (body: unknown, ok = true) => Promise.resolve({ ok, status: ok ? 200 : 500, json: async () => body });
const row = (over: Record<string, unknown> = {}) => ({
  from_status: "enquiry", to_status: "university_selection", from_sub_status: null, to_sub_status: null, outcome: null, outcome_label: null,
  next_action: null, created_at: "2026-10-20T10:00:00Z", changed_at: "2026-10-20T10:00:00Z", ...over,
});

describe("ApplicationStatusHistory", () => {
  it("shows loading, then each row with stage, sub-status, outcome, author and note", async () => {
    const fetchMock = vi.fn(() =>
      json({
        history: [
          row({ to_sub_status: "documents_pending", changed_by: "Asha Counsellor", notes: "Chasing the transcript", reason: null }),
          row({ from_status: "university_selection", outcome: "on_hold", outcome_label: "On hold", changed_by: "Asha Counsellor", notes: "Outcome: On hold -- Awaiting funds", reason: "Awaiting funds" }),
          row({ from_status: "university_selection", outcome: "cleared", outcome_label: "Cleared", changed_by: null, notes: null, reason: "Funds arrived" }),
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationStatusHistory applicationId="a1" />);
    expect(screen.getByText("Loading status history…")).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Status history" });
    expect(fetchMock).toHaveBeenCalledWith(URL);
    const [first, held, resumed] = within(list).getAllByRole("listitem");
    expect(first.textContent).toContain("Enquiry → University selection (Documents pending)");
    expect(first.textContent).toContain("Asha Counsellor");
    expect(first.textContent).toContain("Chasing the transcript");
    expect(within(held).getByText("On hold")).toBeTruthy();
    expect(held.textContent).toContain("Outcome: On hold -- Awaiting funds");
    expect(held.textContent).not.toContain("Reason:"); // the note already carries it
    expect(resumed.textContent).toContain("Reason: Funds arrived");
  });

  it("shows only what a student row carries", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ history: [row({ outcome: "rejected", outcome_label: "Rejected" })] })));
    render(<ApplicationStatusHistory applicationId="a1" />);
    const item = within(await screen.findByRole("list", { name: "Status history" })).getByRole("listitem");
    expect(within(item).getByText("Rejected")).toBeTruthy();
    expect(item.textContent).not.toContain("Reason");
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ history: [] })));
    render(<ApplicationStatusHistory applicationId="a1" />);
    expect(await screen.findByText("No status changes recorded yet.")).toBeTruthy();
  });

  it("shows an error with a retry that reloads", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "x" }, false)).mockReturnValueOnce(json({ history: [row()] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationStatusHistory applicationId="a1" />);
    expect(await screen.findByText("Unable to load the status history.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Status history" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
