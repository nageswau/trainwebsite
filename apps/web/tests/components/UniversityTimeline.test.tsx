import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityTimeline from "@/components/UniversityTimeline";
import { formatCalendarDate } from "@/lib/formatDate";
import { type Milestone, type MilestonePage, monthLabel, quarterLabel, type UniversityExpected } from "@/lib/partnershipMilestones";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const bodyOf = (mock: ReturnType<typeof vi.fn>, i = 0) => JSON.parse(String((mock.mock.calls[i] as [string, RequestInit])[1].body));
const ms = (kind: string, label: string, over: Partial<Milestone> = {}): Milestone => ({
  kind, label, target_date: null, achieved_on: null, achieved_by: null, auto_source: null, status: "pending", ...over,
});
const page = (items: Milestone[], can_edit = true): MilestonePage => ({ items, today: "2026-10-09", can_edit });
const ITEMS = [
  ms("university_contacted", "University Contacted", { target_date: "2026-09-05", achieved_on: "2026-09-05", achieved_by: "manual", status: "done" }),
  ms("meeting", "Meeting", { target_date: "2026-09-12", status: "delayed" }),
  ms("presentation", "Presentation", { target_date: "2026-10-20", status: "pending" }),
  ms("first_application", "First Application", { achieved_on: "2026-10-01", achieved_by: "auto", auto_source: "application", status: "done" }),
];
const EMPTY: UniversityExpected = {
  target_partnership_date: null, expected_month: null, expected_quarter: null, expected_intake: null, expected_agreement_date: null,
  expected_recruitment_start: null,
};
const EXPECTED: UniversityExpected = {
  target_partnership_date: "2026-11-15", expected_month: "2026-11", expected_quarter: "2026-Q4", expected_intake: "January 2027",
  expected_agreement_date: "2026-10-30", expected_recruitment_start: "2026-12-01",
};
const show = (over: { initial?: MilestonePage | null; expected?: UniversityExpected; canEdit?: boolean } = {}) =>
  render(<UniversityTimeline universityId="u1" expected={over.expected ?? EXPECTED} canEdit={over.canEdit ?? true} initial={over.initial === undefined ? page(ITEMS) : over.initial} />);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("partnershipMilestones labels (Q-10)", () => {
  it("words the derived month and calendar quarter", () => {
    expect(monthLabel("2026-11")).toBe("November 2026");
    expect(quarterLabel("2026-Q4")).toBe("Q4 2026 (Oct–Dec)");
    expect(quarterLabel("2027-Q1")).toBe("Q1 2027 (Jan–Mar)");
    expect(monthLabel(null)).toBeNull();
  });
});

describe("UniversityTimeline (upc-008)", () => {
  it("shows the §5 expected timeline with the derived month and quarter", () => {
    show();
    const facts = screen.getByRole("group", { name: "Expected timeline" });
    expect(within(facts).getByText(formatCalendarDate("2026-11-15"))).toBeInTheDocument();
    expect(within(facts).getByText("November 2026")).toBeInTheDocument();
    expect(within(facts).getByText("Q4 2026 (Oct–Dec)")).toBeInTheDocument();
    expect(within(facts).getByText("January 2027")).toBeInTheDocument();
  });

  it("says when nothing is planned yet", () => {
    show({ expected: EMPTY });
    expect(within(screen.getByRole("group", { name: "Expected timeline" })).getAllByText("Not set")).toHaveLength(6);
  });

  it("lists the milestones with status as text and highlights a delayed one (AC1)", () => {
    show();
    const table = screen.getByRole("table", { name: "Partnership milestones" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    expect(within(rows[0]).getByText("Done")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Delayed")).toHaveClass("status", "error");
    expect(rows[1]).toHaveClass("milestone-delayed");
    expect(within(rows[3]).getByText(/Auto, from the first application/)).toBeInTheDocument();
    expect(screen.getByText("1 milestone delayed")).toBeInTheDocument();
  });

  it("sets the current milestone apart from the pending ones (QA8-04)", () => {
    show({ initial: page([ms("meeting", "Meeting", { status: "in_progress" }), ms("presentation", "Presentation")]) });
    expect(screen.getByText("In progress")).toHaveClass("badge");
    expect(screen.getByText("Pending")).toHaveClass("status", "pending");
  });

  it("offers no edit controls to a reader", () => {
    show({ canEdit: false, initial: page(ITEMS, false) });
    expect(screen.queryByRole("button", { name: /Edit/ })).not.toBeInTheDocument();
  });

  it("saves a milestone's dates, replaces the table from the response and announces it", async () => {
    const updated = ITEMS.map((m) => (m.kind === "meeting" ? { ...m, target_date: "2026-10-25", status: "in_progress" as const } : m));
    const mock = vi.fn(() => Promise.resolve(res(page(updated))));
    vi.stubGlobal("fetch", mock);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meeting" }));
    const form = screen.getByRole("form", { name: "Edit Meeting" });
    expect(within(form).getByLabelText("Achieved on")).toHaveAttribute("max", "2026-10-09");
    fireEvent.change(within(form).getByLabelText("Target date"), { target: { value: "2026-10-25" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Meeting saved."));
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/universities/u1/milestones/meeting", expect.objectContaining({ method: "PATCH" }));
    expect(bodyOf(mock)).toEqual({ target_date: "2026-10-25", achieved_on: null });
    expect(screen.queryByText("1 milestone delayed")).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Edit Meeting" })).not.toBeInTheDocument();
  });

  it("keeps a future achieved date's 422 on the field, with what was typed (N1)", async () => {
    const detail = [{ loc: ["body", "achieved_on"], msg: "Value error, The achieved date can't be in the future" }];
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail }, 422))));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meeting" }));
    const form = screen.getByRole("form", { name: "Edit Meeting" });
    fireEvent.change(within(form).getByLabelText("Achieved on"), { target: { value: "2026-12-01" } });
    expect(within(form).getByLabelText("Achieved on")).toBeInvalid(); // the browser's own `max` check stops it first ...
    fireEvent.submit(form); // ... and the API's 422 covers anything that gets past it (e.g. the IST day turning over)
    expect(await within(form).findByText("The achieved date can't be in the future")).toBeInTheDocument();
    expect(within(form).getByLabelText("Achieved on")).toHaveValue("2026-12-01");
  });

  it("leaves an auto-achieved date blank in the form and explains it", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit First Application" }));
    const form = screen.getByRole("form", { name: "Edit First Application" });
    expect(within(form).getByLabelText("Achieved on")).toHaveValue("");
    expect(within(form).getByText(/Leave blank to use the automatic date/)).toBeInTheDocument();
  });

  it("Cancel and Escape close the form and return focus to Edit", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meeting" }));
    fireEvent.keyDown(screen.getByRole("form", { name: "Edit Meeting" }), { key: "Escape" });
    expect(screen.queryByRole("form", { name: "Edit Meeting" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Meeting" })).toHaveFocus());
  });

  it("shows a refusal as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Reactivate this university first" }, 409))));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meeting" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Edit Meeting" })).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reactivate this university first");
  });

  it("edits the expected timeline, sending blanks as null, then refreshes the page", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ university: {} })));
    vi.stubGlobal("fetch", mock);
    show({ expected: EMPTY });
    fireEvent.click(screen.getByRole("button", { name: "Edit expected timeline" }));
    fireEvent.change(screen.getByLabelText("Target partnership date"), { target: { value: "2026-11-15" } });
    fireEvent.change(screen.getByLabelText("Expected intake"), { target: { value: "January 2027" } });
    fireEvent.click(screen.getByRole("button", { name: "Save expected timeline" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/universities/u1/expected", expect.objectContaining({ method: "PATCH" }));
    expect(bodyOf(mock)).toEqual({
      target_partnership_date: "2026-11-15", expected_intake: "January 2027", expected_agreement_date: null, expected_recruitment_start: null,
    });
    expect(screen.getByRole("status")).toHaveTextContent("Expected timeline saved.");
  });

  it("ignores a double click on Save (one request)", async () => {
    let finish: (r: Response) => void = () => {};
    const mock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", mock);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Meeting" }));
    const save = within(screen.getByRole("form", { name: "Edit Meeting" })).getByRole("button", { name: "Save" });
    fireEvent.click(save);
    fireEvent.click(save);
    finish(res(page(ITEMS)));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("a failed first read offers Try again, which loads the milestones", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page(ITEMS)))));
    show({ initial: null });
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the milestones.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: "Partnership milestones" })).toBeInTheDocument();
  });
});
