import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolPromotionPanel from "@/components/SchoolPromotionPanel";
import type { PromotionStudent } from "@/components/SchoolPromotionRow";

// ENH-004 -- the coordinator's rollover screen (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md §7, §7.1).
const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const YEAR = { id: "y-new", label: "2026-27" };
const OLD_YEAR = "y-old";

function student(n: string, over: Partial<PromotionStudent> = {}): PromotionStudent {
  return { id: `id-${n}`, student_code: `S-${n}`, full_name: `Child ${n}`, grade_or_class: "Grade 8-A", grade_level: 8, academic_year_id: OLD_YEAR, ...over };
}

const row = (name: string) => screen.getAllByRole("listitem").find((li) => li.textContent?.includes(name))!;
const box = (name: RegExp) => screen.getByRole("checkbox", { name }) as HTMLInputElement;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init))));
}

function reviewAndConfirm(count: number) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`Review changes \\(${count}\\)`) }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm promotion" }));
}

afterEach(() => {
  cleanup();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

describe("empty and blocked states", () => {
  it("explains there is nothing to do when no academic year is active, and renders no list", () => {
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={null} />);
    expect(screen.getByText("No active academic year")).toBeTruthy();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("offers a way forward when the roster is empty", () => {
    render(<SchoolPromotionPanel students={[]} activeYear={YEAR} />);
    expect(screen.getByText("No students on the roster yet")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Go to the student roster/ }).getAttribute("href")).toBe("/school/coordinator/students");
  });

  it("locks a student already in the active year and says so in text", () => {
    render(<SchoolPromotionPanel students={[student("L", { academic_year_id: YEAR.id })]} activeYear={YEAR} />);
    expect(within(row("Child L")).getByText("Already in 2026-27")).toBeTruthy();
    expect(box(/Child L/).disabled).toBe(true);
  });

  it("warns, before anything is submitted, about students the server will refuse", () => {
    render(<SchoolPromotionPanel students={[student("T", { grade_or_class: "Grade 12", grade_level: 12 }), student("N", { grade_level: null })]} activeYear={YEAR} />);
    expect(within(row("Child T")).getByText("Grade 12 is the highest grade and cannot be promoted. Choose Hold back.")).toBeTruthy();
    expect(within(row("Child N")).getByText("Grade level is not set. Set it on the roster before promoting.")).toBeTruthy();
  });
});

describe("filtering", () => {
  it("filters by grade level, announces the count, and clears the selection", () => {
    render(<SchoolPromotionPanel students={[student("A"), student("B", { grade_level: 9, grade_or_class: "Grade 9-A" })]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    fireEvent.change(screen.getByLabelText("Grade level"), { target: { value: "9" } });
    expect(screen.getByText("Showing 1 of 2 students")).toBeTruthy();
    expect(screen.queryByText(/Child A/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Grade level"), { target: { value: "all" } });
    expect(box(/Child A/).checked).toBe(false);
  });

  it("offers a way back from a filter with no matches", () => {
    render(<SchoolPromotionPanel students={[student("A", { grade_level: null })]} activeYear={YEAR} />);
    fireEvent.change(screen.getByLabelText("Grade level"), { target: { value: "8" } });
    expect(screen.getByText("No students match this filter")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show all grades" }));
    expect(screen.getByText(/Child A/)).toBeTruthy();
  });
});

describe("the confirm step", () => {
  it("asks for explicit confirmation, focuses Confirm, and Escape backs out and returns focus to Review", () => {
    render(<SchoolPromotionPanel students={[student("A"), student("B")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    fireEvent.click(box(/Child B/));
    fireEvent.change(within(row("Child B")).getByLabelText("Action"), { target: { value: "hold_back" } });
    fireEvent.click(screen.getByRole("button", { name: /Review changes \(2\)/ }));

    expect(screen.getByText("Promote 1 and hold back 1 into 2026-27? This changes the current grade of each selected student.")).toBeTruthy();
    const confirm = screen.getByRole("button", { name: "Confirm promotion" });
    expect(document.activeElement).toBe(confirm);

    fireEvent.keyDown(confirm, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Confirm promotion" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Review changes \(2\)/ }));
  });

  it("disables Review with nothing selected", () => {
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    expect((screen.getByRole("button", { name: /Review changes \(0\)/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("refuses more than 500 students in one request, and says why", () => {
    render(<SchoolPromotionPanel students={Array.from({ length: 501 }, (_, i) => student(String(i)))} activeYear={YEAR} />);
    // By id and by text, not getByLabelText/getByRole: with ~500 rows Testing Library's label lookup over jsdom's
    // `element.labels` is super-linear (measured: 16 s at 120 rows, minutes at 501) and would stall the run. The
    // component itself is fast here (measured at 501 rows: render ~0.5 s, select-all ~0.13 s).
    fireEvent.click(document.getElementById("promotion-select-all")!);
    expect(screen.getByText("501 selected. Select at most 500 at a time.")).toBeTruthy();
    expect((screen.getByText(/Review changes \(501\)/) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("submitting", () => {
  const outcome = {
    academic_year: YEAR,
    counts: { promoted: 1, held_back: 0, failed: 1, skipped: 0 },
    results: [
      { student_id: "id-A", status: "promoted", reason: null, message: null, grade_level: 9, grade_or_class: "Grade 9-A" },
      { student_id: "id-T", status: "failed", reason: "terminal_grade", message: "Grade 12 is the highest grade; graduation is not supported yet.", grade_level: 12, grade_or_class: "Grade 12" },
    ],
  };

  it("sends exactly the chosen items, shows the server's outcome per row, keeps failed rows selected, and refreshes", async () => {
    let sent: unknown = null;
    stubFetch((_url, init) => {
      sent = JSON.parse(String(init?.body));
      return json(outcome);
    });
    render(<SchoolPromotionPanel students={[student("A"), student("T", { grade_or_class: "Grade 12", grade_level: 12 })]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    fireEvent.click(box(/Child T/));
    fireEvent.change(within(row("Child A")).getByLabelText("New label (optional)"), { target: { value: "Grade 9 (Gold)" } });
    reviewAndConfirm(2);

    await screen.findByText("Done for 2026-27: 1 promoted, 0 held back, 1 not changed, 0 skipped.");
    expect(sent).toEqual({ items: [{ student_id: "id-A", action: "promote", grade_or_class: "Grade 9 (Gold)" }, { student_id: "id-T", action: "promote" }] });
    expect(fetch).toHaveBeenCalledWith("/api/v1/school/students/promotions", expect.objectContaining({ method: "POST" }));
    // The server's per-row outcome is shown at once, before the refresh lands.
    expect(within(row("Child A")).getByText("Promoted")).toBeTruthy();
    expect(within(row("Child A")).getByText(/Grade 9-A/)).toBeTruthy();
    expect(within(row("Child A")).getByText("Now in 2026-27")).toBeTruthy();
    expect(within(row("Child T")).getByText("Not changed")).toBeTruthy();
    expect(within(row("Child T")).getByText("Grade 12 is the highest grade; graduation is not supported yet.")).toBeTruthy();
    expect(box(/Child T/).checked).toBe(true);
    expect(box(/Child A/).disabled).toBe(true);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    // Focus moves to the summary because the confirm button that had it is gone.
    expect(document.activeElement?.textContent).toContain("Done for 2026-27");
  });

  it("does not send an override with hold back", async () => {
    let sent: { items: unknown[] } | null = null;
    stubFetch((_url, init) => {
      sent = JSON.parse(String(init?.body));
      return json({ academic_year: YEAR, counts: { promoted: 0, held_back: 1, failed: 0, skipped: 0 }, results: [{ student_id: "id-A", status: "held_back", reason: null, message: null, grade_level: 8, grade_or_class: "Grade 8-A" }] });
    });
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    fireEvent.change(within(row("Child A")).getByLabelText("New label (optional)"), { target: { value: "Grade 9" } });
    fireEvent.change(within(row("Child A")).getByLabelText("Action"), { target: { value: "hold_back" } });
    reviewAndConfirm(1);

    await screen.findByText(/Done for 2026-27/);
    expect(sent).toEqual({ items: [{ student_id: "id-A", action: "hold_back" }] });
    expect(within(row("Child A")).getByText("Held back")).toBeTruthy();
  });
});

describe("error states", () => {
  it("shows a server refusal as an alert and keeps the selection", async () => {
    stubFetch(() => json({ detail: "One or more students are not at your institution" }, 403));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("not at your institution");
    expect(box(/Child A/).checked).toBe(true);
    expect(screen.queryByRole("button", { name: "Confirm promotion" })).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("renders FastAPI's list-shaped validation errors as text", async () => {
    stubFetch(() => json({ detail: [{ msg: "List should have at most 500 items" }] }, 422));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);
    expect((await screen.findByRole("alert")).textContent).toContain("List should have at most 500 items");
  });

  it("says a dropped connection may or may not have applied, keeps the selection, and that repeating is safe", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("did not complete");
    expect(alert.textContent).toContain("repeating it is safe");
    expect(box(/Child A/).checked).toBe(true);
  });

  // QA-003: the Confirm button (bottom of a long list) is unmounted on failure, so focus is lost; the banner sits at the
  // top of the panel and can be scrolled out of view. Focusing it scrolls it into view and moves keyboard users to it,
  // exactly as the success summary already does.
  it.each([
    ["a server refusal", () => stubFetch(() => json({ detail: "One or more students are not at your institution" }, 403))],
    ["a non-JSON server error", () => stubFetch(() => new Response("Bad gateway", { status: 502 }))],
    ["a dropped connection", () => vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))))],
  ])("moves focus to the error banner after %s", async (_name, arrange) => {
    arrange();
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(document.activeElement).toBe(alert));
  });

  it("does not leave a stale error banner after a later successful submit", async () => {
    stubFetch(() => json({ detail: "Another promotion is in progress; retry" }, 409));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);
    await screen.findByRole("alert");

    stubFetch(() => json({ academic_year: YEAR, counts: { promoted: 1, held_back: 0, failed: 0, skipped: 0 }, results: [{ student_id: "id-A", status: "promoted", reason: null, message: null, grade_level: 9, grade_or_class: "Grade 9-A" }] }));
    reviewAndConfirm(1);
    await screen.findByText(/Done for/);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// QA-004..007 (second QA round, all Low).
describe("unreadable success response (QA-004)", () => {
  it.each([
    ["an empty JSON object", () => json({})],
    ["a non-JSON body", () => new Response("<html>proxy login page</html>", { status: 200, headers: { "Content-Type": "text/html" } })],
    ["a report without counts", () => json({ academic_year: YEAR, results: [] })],
  ])("shows an error instead of crashing the page on %s, and keeps the selection", async (_name, respond) => {
    stubFetch(() => respond());
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("could not be read");
    expect(alert.textContent).toContain("repeating it is safe");
    expect(box(/Child A/).checked).toBe(true);
    expect(screen.queryByText(/Done for/)).toBeNull();
  });
});

describe("failure reasons are shown in plain language (QA-005)", () => {
  const failedReport = (reason: string | null, message: string) => ({
    academic_year: YEAR,
    counts: { promoted: 0, held_back: 0, failed: 1, skipped: 0 },
    results: [{ student_id: "id-A", status: "failed", reason, message, grade_level: 8, grade_or_class: "8A" }],
  });

  it.each([
    ["label_unparseable", "grade_or_class has no grade number to advance; supply grade_or_class", /can't be advanced automatically.*New label/],
    ["label_unparseable", "grade_or_class does not match grade_level; supply grade_or_class", /can't be advanced automatically.*New label/],
    ["grade_level_not_set", "grade_level is not set; set it on the student before promoting.", /Grade level is not set\. Set it on the roster/],
  ])("maps %s to wording a coordinator can act on, without the API's field names", async (reason, raw, friendly) => {
    stubFetch(() => json(failedReport(reason, raw)));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    await screen.findByText(/Done for/);
    const text = within(row("Child A")).getByText(friendly).textContent!;
    expect(text).not.toMatch(/grade_or_class|grade_level/);
    expect(within(row("Child A")).queryByText(raw)).toBeNull();
  });

  it("falls back to the server's message for a reason it does not know", async () => {
    stubFetch(() => json(failedReport("some_future_reason", "Something specific from the server.")));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);
    await screen.findByText(/Done for/);
    expect(within(row("Child A")).getByText("Something specific from the server.")).toBeTruthy();
  });
});

describe("while a request is in flight (QA-006)", () => {
  it("locks the list, the filters and select-all, marks the list busy, and unlocks after the answer", async () => {
    let release: (r: Response) => void = () => {};
    stubFetch(() => new Promise<Response>((resolve) => { release = resolve; }) as unknown as Response);
    render(<SchoolPromotionPanel students={[student("A"), student("B")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    await screen.findByRole("button", { name: "Promoting…" });
    expect(box(/Child A/).disabled).toBe(true);
    expect(box(/Child B/).disabled).toBe(true);
    expect((within(row("Child B")).getByLabelText("Action") as HTMLSelectElement).disabled).toBe(true);
    expect((within(row("Child B")).getByLabelText("New label (optional)") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Grade level") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByLabelText("Select all shown") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("list").getAttribute("aria-busy")).toBe("true");

    release(json({ academic_year: YEAR, counts: { promoted: 1, held_back: 0, failed: 0, skipped: 0 }, results: [{ student_id: "id-A", status: "promoted", reason: null, message: null, grade_level: 9, grade_or_class: "Grade 9-A" }] }));
    await screen.findByText(/Done for/);
    expect(box(/Child B/).disabled).toBe(false);
    expect((screen.getByLabelText("Grade level") as HTMLSelectElement).disabled).toBe(false);
  });
});

describe("an expired session on submit (QA-007)", () => {
  it("says the session expired and links to sign in again, keeping the selection", async () => {
    stubFetch(() => json({ detail: "Not authenticated" }, 401));
    render(<SchoolPromotionPanel students={[student("A")]} activeYear={YEAR} />);
    fireEvent.click(box(/Child A/));
    reviewAndConfirm(1);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Your session has expired");
    expect(within(alert).getByRole("link", { name: "Sign in again" }).getAttribute("href")).toBe("/overseas/login");
    expect(box(/Child A/).checked).toBe(true);
  });
});
