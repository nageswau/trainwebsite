import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolSkillBatchHeader from "@/components/SchoolSkillBatchHeader";

import { detail, json, stubFetch } from "./skillFixtures";

// ENH-011 spec §7: the batch header -- details, inline edit, close/reopen, and the closed banner.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("SchoolSkillBatchHeader", () => {
  it("shows the batch as the page heading with its details in words", () => {
    render(<SchoolSkillBatchHeader batch={detail()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Public speaking" })).toBeTruthy();
    expect(screen.getByText(/Soft Skills/)).toBeTruthy();
    expect(screen.getByText(/Sunrise School/)).toBeTruthy();
    expect(screen.getByText(/R\. Iyer/)).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.queryByText(/This batch is closed/)).toBeNull();
  });

  it("edits the details inline and sends only the fields", async () => {
    const fetchMock = stubFetch(() => json({ ...detail(), title: "Debate" }));
    render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Title"));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Debate" } });
    fireEvent.change(screen.getByLabelText("Trainer name (optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-batches/b1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ title: "Debate", topic: "Presentation", trainer_name: null, start_date: "2026-10-01", end_date: "2026-12-01" });
    expect(screen.getByRole("status").textContent).toBe("Details saved.");
  });

  it("checks the date order before sending an edit (QA-05)", () => {
    const fetchMock = stubFetch(() => json(detail()));
    render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("End date (optional)"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(fetchMock).not.toHaveBeenCalled();
    const end = screen.getByLabelText("End date (optional)");
    expect(end.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(end.getAttribute("aria-describedby")!)!.textContent).toBe("The end date must be on or after the start date");
  });

  it("clears a success message after a few seconds so they do not pile up (QA-08)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubFetch(() => json(detail({ status: "closed" })));
    render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Close batch" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Batch closed."));
    await act(async () => { await vi.advanceTimersByTimeAsync(7000); });
    expect(screen.getByRole("status").textContent).toBe("Batch closed."); // still there before the delay
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByRole("status").textContent).toBe("");
    vi.useRealTimers();
  });

  it("cancelling the edit returns focus to the Edit button", () => {
    render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit details" }));
  });

  it("closes and reopens the batch", async () => {
    const fetchMock = stubFetch(() => json(detail({ status: "closed" })));
    const { rerender } = render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Close batch" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ status: "closed" });
    rerender(<SchoolSkillBatchHeader batch={detail({ status: "closed" })} />);
    expect(screen.getByText(/This batch is closed\. Reopen it to add students, sessions, attendance or scores\./)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reopen batch" })).toBeTruthy();
  });

  it("shows the server's reason when a change is refused", async () => {
    stubFetch(() => json({ detail: "Skills batch not found" }, 404));
    render(<SchoolSkillBatchHeader batch={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Close batch" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Skills batch not found");
  });
});
