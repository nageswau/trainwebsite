import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-018 -- the coordinator/principal Feedback page (spec §7.1): states, read-only principal view, submit/duplicate outcomes, paging.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SAVED = { id: "fb-1", activity_id: "a1", trainer_name: null, rating: 3, satisfaction: 4, feedback: "Good", suggestions: null, submitted_by_name: "Coordinator", submitted_at: "2026-09-21T09:00:00Z" };
const row = (id: string, feedback: typeof SAVED | null = null): FeedbackActivity => ({ activity_id: id, title: `Seminar ${id}`, activity_type: "career_seminar", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 0, marked: 0 }, feedback });
const page = (items: FeedbackActivity[], total = items.length) => ({ items, total, limit: 25, offset: 0 });
const item = (title: string) => screen.getAllByRole("listitem").find((li) => li.textContent?.includes(title))!;

function fillAndSubmit(text: string) {
  fireEvent.click(screen.getByLabelText("3 – Good", { selector: "input[name=rating]" }));
  fireEvent.click(screen.getByLabelText("4 – Very good", { selector: "input[name=satisfaction]" }));
  fireEvent.change(screen.getByLabelText("Feedback"), { target: { value: text } });
  fireEvent.submit(screen.getByRole("button", { name: "Submit feedback" }).closest("form")!);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolActivityFeedbackPanel", () => {
  it("adds Feedback to the coordinator and principal navigation", () => {
    expect(SCHOOL_NAV.coordinator.map((n) => n.href)).toContain("/school/coordinator/feedback");
    expect(SCHOOL_NAV.principal.map((n) => n.href)).toContain("/school/principal/feedback");
  });

  it("shows the empty state with a way to the Activities page", () => {
    render(<SchoolActivityFeedbackPanel initial={page([])} canSubmit />);
    expect(screen.getByRole("heading", { name: "No completed Edusphere activities yet." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Activities" })).toHaveAttribute("href", "/school/coordinator/activities");
  });

  it("words status and participation in text, and shows stored feedback in a disclosure", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED), row("a2")])} canSubmit />);
    expect(within(item("Seminar a1")).getByText("Submitted")).toBeTruthy();
    expect(within(item("Seminar a2")).getByText("Awaiting feedback")).toBeTruthy();
    expect(within(item("Seminar a2")).getByText(/Not marked/)).toBeTruthy();
    fireEvent.click(within(item("Seminar a1")).getByText("View feedback"));
    expect(within(item("Seminar a1")).getByText("3 – Good")).toBeTruthy();
  });

  it("principal view is read-only", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit={false} />);
    expect(screen.queryByRole("button", { name: /Give feedback/ })).toBeNull();
    render(<SchoolActivityFeedbackPanel initial={page([])} canSubmit={false} />);
    expect(screen.queryByRole("link", { name: "Go to Activities" })).toBeNull();
  });

  it("submitting updates the row in place, announces it and moves focus to the status message", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ ...SAVED, activity_id: "a2" }, 201))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
    fillAndSubmit("Good");
    const status = await screen.findByText("Feedback saved for Seminar a2.");
    expect(within(item("Seminar a2")).getByText("Submitted")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(status.closest("[role=status]")));
  });

  it("cancel closes the form and puts focus back on its button", async () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Submit feedback" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Give feedback for Seminar a2" })));
  });

  it("on 409 it reloads the list so the stored feedback is shown", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(String(url).includes("activity-feedback") ? json(page([row("a2", SAVED)])) : json({ detail: "Feedback has already been submitted for this activity" }, 409))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
    fillAndSubmit("Again");
    expect(await screen.findByText(/already been submitted/)).toBeTruthy();
    await waitFor(() => expect(within(item("Seminar a2")).getByText("Submitted")).toBeTruthy());
  });

  it("filter change fetches that status; a failed fetch shows a retryable alert", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({}, 500)).mockResolvedValueOnce(json(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)])} canSubmit />);
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "awaiting" } });
    expect((await screen.findByRole("alert")).textContent).toMatch(/Could not load/);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/school/activity-feedback?status=awaiting&limit=25&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Nothing awaiting feedback." })).toBeTruthy();
  });

  it("a failed filter load never leaves the previous filter's rows under the new label (QA-018-06)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({}, 500))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED), row("a2")])} canSubmit />);
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "submitted" } });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Completed Edusphere activities" })).toBeNull();
    expect(screen.queryByText(/Showing/)).toBeNull();
  });

  it("an expired session says so and links to sign-in instead of offering a retry that cannot work (QA-018-14)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: "Not authenticated" }, 401))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)])} canSubmit />);
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "awaiting" } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Your session has expired/);
    expect(within(alert).getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/overseas/login");
    expect(within(alert).queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("the filter stays enabled while loading, so keyboard focus is not thrown away (QA-018-05)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)])} canSubmit />);
    const select = screen.getByLabelText("Show");
    select.focus();
    fireEvent.change(select, { target: { value: "awaiting" } });
    expect(select).not.toBeDisabled();
    expect(document.activeElement).toBe(select);
  });

  it("after Load more, focus moves to the first newly loaded item (QA-018-04)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ items: [row("a2")], total: 2, limit: 25, offset: 1 }))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)], 2)} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Showing 2 of 2");
    await waitFor(() => expect(document.activeElement).toBe(item("Seminar a2")));
  });

  it("?activity focus: opens that awaiting activity's form and offers a way back to all activities (QA-018-09)", async () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit focusActivityId="a2" />);
    expect(screen.getByRole("heading", { name: "Feedback: Seminar a2" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Show all activities" })).toHaveAttribute("href", "/school/coordinator/feedback");
  });

  it("?activity focus on an activity that already has feedback shows it expanded", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)])} canSubmit focusActivityId="a1" />);
    expect(screen.queryByRole("button", { name: "Submit feedback" })).toBeNull();
    expect(within(item("Seminar a1")).getByText("3 – Good")).toBeVisible();
  });

  it("?activity focus on an activity that is not eligible explains it instead of the generic empty state", () => {
    render(<SchoolActivityFeedbackPanel initial={page([])} canSubmit focusActivityId="zz" />);
    expect(screen.getByRole("heading", { name: "This activity is not open for feedback." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Show all activities" })).toBeTruthy();
  });

  it("loads more and says how many are shown", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ items: [row("a2")], total: 2, limit: 25, offset: 1 }))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)], 2)} canSubmit />);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 2 of 2")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});
