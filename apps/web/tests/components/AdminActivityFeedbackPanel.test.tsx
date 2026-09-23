import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminActivityFeedbackPanel from "@/components/AdminActivityFeedbackPanel";
import type { AdminActivityFeedback } from "@/lib/activityFeedback";
import { PORTAL_NAV } from "@/lib/navigation";

// ENH-018 -- Edusphere management's cross-school list (spec §7.3): busy, cards, filter, paging, empty and failure states.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SCHOOLS = [{ id: "s1", name: "Sunrise School" }, { id: "s2", name: "Lakeview School" }];
const fb = (n: string, school = SCHOOLS[0]): AdminActivityFeedback => ({
  id: `fb-${n}`, activity_id: `a-${n}`, trainer_name: "Ms. Rao", rating: 4, satisfaction: 5, feedback: `Feedback ${n}`, suggestions: null, submitted_by_name: "Fatima", submitted_at: "2026-09-21T09:00:00Z",
  school_id: school.id, school_name: school.name, activity_title: `Seminar ${n}`, activity_type: "campus_visit", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 40, marked: 45 },
});
const page = (items: AdminActivityFeedback[], total = items.length, offset = 0) => ({ items, total, limit: 25, offset });

function stub(handler: (url: string) => Response) {
  const fn = vi.fn((url: string) => Promise.resolve(handler(String(url))));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminActivityFeedbackPanel", () => {
  it("is in the overseas admin navigation", () => {
    expect(PORTAL_NAV["overseas/admin"].map((n) => n.href)).toContain("/overseas/admin/activity-feedback");
  });

  it("shows a busy skeleton, then one card per feedback with school, activity, participation and all fields", async () => {
    stub((url) => (url.endsWith("/schools") ? json(SCHOOLS) : json(page([fb("1")]))));
    render(<AdminActivityFeedbackPanel />);
    expect(document.querySelector("[aria-busy=true]")).toBeTruthy();
    const card = (await screen.findByText("Seminar 1")).closest("li")!;
    for (const text of [/Sunrise School/, /Monthly campus visit/, /40 of 45 present/, "4 – Very good", "5 – Excellent", "Ms. Rao", "Feedback 1"]) {
      expect(within(card).getByText(text)).toBeTruthy();
    }
    expect(document.querySelector("[aria-busy=true]")).toBeNull();
  });

  it("filters by school and pages with Load more", async () => {
    const fetchMock = stub((url) => (url.endsWith("/schools") ? json(SCHOOLS) : url.includes("offset=1") ? json(page([fb("2")], 2, 1)) : json(page([fb("1")], 2))));
    render(<AdminActivityFeedbackPanel />);
    await screen.findByText("Seminar 1");
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Seminar 2")).toBeTruthy();
    await waitFor(() => expect(within(screen.getByLabelText("School")).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(screen.getByLabelText("School"), { target: { value: "s2" } });
    await waitFor(() => expect(fetchMock.mock.calls.map((c) => c[0])).toContain("/api/v1/overseas-admin/school-activity-feedback?school_id=s2&limit=25&offset=0"));
  });

  it("empty state, and a failed load offers Try again", async () => {
    let fail = true;
    stub((url) => (url.endsWith("/schools") ? json(SCHOOLS) : fail ? json({}, 500) : json(page([]))));
    render(<AdminActivityFeedbackPanel />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/Could not load/);
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No feedback submitted yet." })).toBeTruthy();
  });

  it("still lists feedback when the school list cannot load (filter just shows All schools)", async () => {
    stub((url) => (url.endsWith("/schools") ? json({}, 500) : json(page([fb("1")]))));
    render(<AdminActivityFeedbackPanel />);
    expect(await screen.findByText("Seminar 1")).toBeTruthy();
    expect(within(screen.getByLabelText("School")).getAllByRole("option")).toHaveLength(1);
  });
});
