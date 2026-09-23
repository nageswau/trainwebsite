import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ActivityFeedbackForm from "@/components/ActivityFeedbackForm";
import type { FeedbackActivity } from "@/lib/activityFeedback";

// ENH-018 -- the coordinator's feedback form (spec §7.2): every §31 field, keyboard/screen-reader semantics, and each outcome.
const ACTIVITY: FeedbackActivity = { activity_id: "act-1", title: "Career Seminar", activity_type: "career_seminar", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 42, marked: 50 }, feedback: null };
const SAVED = { id: "fb-1", activity_id: "act-1", trainer_name: "Ms. Rao", rating: 4, satisfaction: 5, feedback: "Great", suggestions: null, submitted_by_name: "Coordinator", submitted_at: "2026-09-21T09:00:00Z" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function setup(response: () => Promise<Response>) {
  const fetchMock = vi.fn(response);
  vi.stubGlobal("fetch", fetchMock);
  const handlers = { onSubmitted: vi.fn(), onDuplicate: vi.fn(), onCancel: vi.fn() };
  render(<ActivityFeedbackForm activity={ACTIVITY} {...handlers} />);
  return { fetchMock, ...handlers };
}
function fill() {
  fireEvent.click(screen.getByLabelText("4 – Very good", { selector: "input[name=rating]" }));
  fireEvent.click(screen.getByLabelText("5 – Excellent", { selector: "input[name=satisfaction]" }));
  fireEvent.change(screen.getByLabelText("Trainer / Counsellor (optional)"), { target: { value: "Ms. Rao" } });
  fireEvent.change(screen.getByLabelText("Feedback"), { target: { value: "Great" } });
}
const submit = () => fireEvent.submit(screen.getByRole("button", { name: "Submit feedback" }).closest("form")!);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ActivityFeedbackForm", () => {
  it("moves focus to its heading and labels every §31 field, with scores as grouped radios", () => {
    setup(() => Promise.resolve(json(SAVED, 201)));
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: /Feedback: Career Seminar/ }));
    expect(screen.getByRole("group", { name: "Overall rating" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "School satisfaction" })).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(10);
    expect(screen.getByText(/42 of 50 present/)).toBeTruthy();
    expect(screen.getByLabelText("Feedback")).toHaveAttribute("maxlength", "5000");
    expect(screen.getByLabelText("Feedback")).toHaveAccessibleDescription(/personal details/);
  });

  it("posts the typed values and reports the stored feedback", async () => {
    const { fetchMock, onSubmitted } = setup(() => Promise.resolve(json(SAVED, 201)));
    fill();
    submit();
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(SAVED));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/school/activities/act-1/feedback");
    expect(JSON.parse(String(init.body))).toEqual({ rating: 4, satisfaction: 5, trainer_name: "Ms. Rao", feedback: "Great", suggestions: null });
  });

  it("disables submit while saving", async () => {
    let release!: (r: Response) => void;
    setup(() => new Promise<Response>((resolve) => (release = resolve)));
    fill();
    submit();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    release(json(SAVED, 201));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Saving…" })).toBeNull());
  });

  it("keeps the entry and focuses a readable alert when the server refuses", async () => {
    setup(() => Promise.resolve(json({ detail: [{ msg: "Value error, must not be blank" }] }, 422)));
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Must not be blank");
    await waitFor(() => expect(document.activeElement).toBe(alert));
    expect(screen.getByLabelText("Feedback")).toHaveValue("Great");
  });

  it("hands a 409 (already submitted, e.g. a retry after a lost response) to the parent instead of an error", async () => {
    const { onDuplicate } = setup(() => Promise.resolve(json({ detail: "Feedback has already been submitted for this activity" }, 409)));
    fill();
    submit();
    await waitFor(() => expect(onDuplicate).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an expired session says so, links to sign-in and keeps the entry (QA-018-14)", async () => {
    setup(() => Promise.resolve(json({ detail: "Not authenticated" }, 401)));
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Your session has expired/);
    expect(alert.textContent).toMatch(/entry is kept/);
    expect(within(alert).getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/overseas/login");
    expect(screen.getByLabelText("Feedback")).toHaveValue("Great");
  });

  it("says the entry is kept when the network drops, and Cancel calls back", async () => {
    const { onCancel } = setup(() => Promise.reject(new TypeError("Failed to fetch")));
    fill();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/your entry is kept/);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
