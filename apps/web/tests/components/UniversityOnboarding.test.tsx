import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityOnboarding from "@/components/UniversityOnboarding";
import { formatCalendarDate } from "@/lib/formatDate";
import type { OnboardingItem, OnboardingPage } from "@/lib/universityOnboarding";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const bodyOf = (mock: ReturnType<typeof vi.fn>, i = 0) => JSON.parse(String((mock.mock.calls[i] as [string, RequestInit])[1].body));
const item = (kind: string, label: string, over: Partial<OnboardingItem> = {}): OnboardingItem => ({
  kind, label, status: "not_started", completed_by: null, completed_on: null, owner: null, due_date: null, note: null, ...over,
});
const ITEMS = [
  item("counselor_training", "Counselor training", { status: "completed", completed_by: "manual", completed_on: "2026-10-08", owner: { id: "p1", full_name: "Priya Manager" } }),
  item("product_training", "Product training", { status: "in_progress", due_date: "2026-10-20", note: "Slides ready" }),
  item("course_database_updated", "Course database updated", { status: "completed", completed_by: "auto" }),
  item("first_student_campaign", "First student campaign"),
];
const page = (over: Partial<OnboardingPage> = {}): OnboardingPage => ({
  started: true, started_on: "2026-10-01", status: "in_progress", completed_count: 2, items: ITEMS, can_edit: true, ...over,
});
const show = (initial: OnboardingPage | null = page()) => render(<UniversityOnboarding universityId="u1" initial={initial} />);
const rowOf = (label: string) => screen.getByRole("rowheader", { name: label }).closest("tr") as HTMLElement;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityOnboarding (upc-027)", () => {
  it("says onboarding waits for a signed agreement (OB3)", () => {
    show(page({ started: false, started_on: null, status: "not_started", completed_count: 0, can_edit: false }));
    expect(screen.getByRole("heading", { name: "Partner onboarding" })).toBeInTheDocument();
    expect(screen.getByText("Onboarding starts when an agreement is signed.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("lists the items with the overall status and statuses as text (AC1, OB6, OB7)", () => {
    show();
    const summary = screen.getByText(/2 of 4 completed/).closest("p") as HTMLElement;
    expect(within(summary).getByText("In Progress")).toHaveClass("badge");
    expect(screen.getByText(new RegExp(`Started ${formatCalendarDate("2026-10-01")}`))).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Partner onboarding checklist" });
    expect(table).toHaveClass("milestone-table"); // QA27-02: the tracker table's phone styling (status pills never wrap)
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    expect(within(rowOf("Counselor training")).getByText("Completed")).toBeInTheDocument();
    expect(within(rowOf("Counselor training")).getByText("Priya Manager")).toBeInTheDocument();
    expect(within(rowOf("Counselor training")).getByText(formatCalendarDate("2026-10-08"))).toBeInTheDocument();
    expect(within(rowOf("Product training")).getByText("Slides ready")).toBeInTheDocument();
    expect(within(rowOf("Course database updated")).getByText(/Automatic: the university has active courses/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument(); // the notice renders only when shown (shared page)
  });

  it("offers no edit for a reader without the right", () => {
    show(page({ can_edit: false }));
    expect(screen.queryByRole("button", { name: /^Edit / })).not.toBeInTheDocument();
  });

  it("edits one item and replaces the checklist with the response (AC3)", async () => {
    const saved = page({ items: [ITEMS[0], { ...ITEMS[1], status: "completed", completed_by: "manual", completed_on: "2026-10-10" }, ITEMS[2], ITEMS[3]], completed_count: 3 });
    const fetchMock = vi.fn().mockResolvedValue(res({ ...saved, stage_advanced: false }));
    vi.stubGlobal("fetch", fetchMock);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Product training" }));
    const form = screen.getByRole("form", { name: "Edit Product training" });
    expect(screen.getByLabelText("Status")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "completed" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "  Done in person " } });
    fireEvent.submit(form);
    fireEvent.submit(form); // a double submit sends once
    await waitFor(() => expect(screen.getByText("Product training saved.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/onboarding/product_training");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("PATCH");
    expect(bodyOf(fetchMock)).toEqual({ status: "completed", owner_user_id: null, due_date: "2026-10-20", note: "Done in person" });
    expect(screen.getByText(/3 of 4 completed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Product training" })).toHaveFocus();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not send a status for the automatic course item", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ...page(), stage_advanced: false }));
    vi.stubGlobal("fetch", fetchMock);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Course database updated" }));
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-01" } });
    fireEvent.submit(screen.getByRole("form", { name: "Edit Course database updated" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf(fetchMock)).toEqual({ owner_user_id: null, due_date: "2026-11-01", note: null });
  });

  it("refreshes the page when the last item activates the partner (AC4)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ...page({ status: "completed", completed_count: 4 }), stage_advanced: true })));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit First student campaign" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "completed" } });
    fireEvent.submit(screen.getByRole("form", { name: "Edit First student campaign" }));
    await waitFor(() => expect(screen.getByText("Onboarding completed: the university is now Partner Activated.")).toBeInTheDocument());
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("takes a fresh server checklist after a page refresh and keeps the notice (QA27-01)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ...page({ status: "completed", completed_count: 4 }), stage_advanced: true })));
    const { rerender } = show();
    fireEvent.click(screen.getByRole("button", { name: "Edit First student campaign" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "completed" } });
    fireEvent.submit(screen.getByRole("form", { name: "Edit First student campaign" }));
    await waitFor(() => expect(screen.getByText("Onboarding completed: the university is now Partner Activated.")).toBeInTheDocument());
    // router.refresh() re-renders the server page: a new `initial` arrives (e.g. a course added elsewhere changed it)
    rerender(<UniversityOnboarding universityId="u1" initial={page({ status: "completed", completed_count: 7, items: ITEMS.map((i) => ({ ...i, note: "fresh" })) })} />);
    expect(screen.getByText(/7 of 4 completed/)).toBeInTheDocument();
    expect(screen.getAllByText("fresh")).toHaveLength(4);
    expect(screen.getByText("Onboarding completed: the university is now Partner Activated.")).toBeInTheDocument();
  });

  it("shows the checklist once a signed agreement refreshes the page (OB2)", () => {
    const { rerender } = show(page({ started: false, started_on: null, status: "not_started", completed_count: 0, can_edit: false }));
    rerender(<UniversityOnboarding universityId="u1" initial={page()} />);
    expect(screen.getByRole("table", { name: "Partner onboarding checklist" })).toBeInTheDocument();
  });

  it("keeps what was typed and shows a field refusal or a conflict", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ detail: [{ loc: ["body", "note"], msg: "String should have at most 500 characters", type: "string_too_long" }] }, 422))
      .mockResolvedValueOnce(res({ detail: { message: "This university is marked lost. Reopen it first.", code: "university_lost" } }, 409));
    vi.stubGlobal("fetch", fetchMock);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Product training" }));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Too long" } });
    fireEvent.submit(screen.getByRole("form", { name: "Edit Product training" }));
    await waitFor(() => expect(screen.getByText("String should have at most 500 characters")).toBeInTheDocument());
    expect(screen.getByLabelText("Note")).toHaveValue("Too long");
    expect(screen.getByLabelText("Note")).toHaveAttribute("aria-invalid", "true");
    fireEvent.submit(screen.getByRole("form", { name: "Edit Product training" }));
    await waitFor(() => expect(screen.getByText("This university is marked lost. Reopen it first.")).toBeInTheDocument());
  });

  it("cancels with Escape and returns focus to the row", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Product training" }));
    fireEvent.keyDown(screen.getByRole("form", { name: "Edit Product training" }), { key: "Escape" });
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Product training" })).toHaveFocus();
  });

  it("offers Try again when the checklist could not load", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(page()));
    vi.stubGlobal("fetch", fetchMock);
    show(null);
    expect(screen.getByText("Unable to load the onboarding checklist.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("table", { name: "Partner onboarding checklist" })).toBeInTheDocument());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/onboarding");
  });
});
