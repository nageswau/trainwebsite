import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CourseForm from "@/components/CourseForm";
import UniversityCourses from "@/components/UniversityCourses";
import type { Course, CoursePage } from "@/lib/courseMaster";

// ccrm-051 (DEC-SCOPE-327): the agent-Master commission on the Add / Edit course form, for super_admin / overseas_admin only.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const course = (over: Partial<Course> = {}): Course => ({
  id: "c1", university_id: "u1", title: "MSc Cyber Security", level: "PG", category: "Computer Science", duration: "1 year", tuition_fee: "", intake: "",
  tuition_amount: null, tuition_currency: null, application_fee: null, application_fee_currency: null, intakes: [], entry_requirements: null, english_test: null,
  english_score: null, scholarships: [], application_process: null, deadline: null, active: true, campus: null, fee_text: null, intake_text: null, icon: null,
  permissions: { can_edit: true }, ...over,
});
const options = { scholarships: [] };
const sent = (fetch: ReturnType<typeof vi.fn>) => JSON.parse(fetch.mock.calls[0][1].body as string);
const form = (props: Partial<Parameters<typeof CourseForm>[0]> = {}) =>
  render(<CourseForm universityId="u1" options={options} canSetCommission={false} label="New course" onSaved={vi.fn()} onCancel={vi.fn()} {...props} />);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fillRequired() {
  fireEvent.change(screen.getByLabelText("Course title (required)"), { target: { value: "MSc AI" } });
  fireEvent.change(screen.getByLabelText("Level (required)"), { target: { value: "PG" } });
  fireEvent.change(screen.getByLabelText("Category (required)"), { target: { value: "Computing" } });
  fireEvent.change(screen.getByLabelText("Duration (required)"), { target: { value: "1 year" } });
}

describe("CourseForm agent commission (ccrm-051)", () => {
  it("is hidden and never sent without canEditAgentCommission", async () => {
    const fetch = vi.fn(async () => res({ course: course() }, 201));
    vi.stubGlobal("fetch", fetch);
    form();
    expect(screen.queryByRole("group", { name: "Agent Master commission" })).toBeNull();
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(sent(fetch)).not.toHaveProperty("agent_commission");
  });

  it("sends a new course's rate and note in the same request; a blank rate sends nothing", async () => {
    const fetch = vi.fn(async () => res({ course: course() }, 201));
    vi.stubGlobal("fetch", fetch);
    form({ canEditAgentCommission: true });
    const group = screen.getByRole("group", { name: "Agent Master commission" });
    fillRequired();
    fireEvent.change(within(group).getByLabelText("Percent", { exact: true }), { target: { value: "12" } });
    fireEvent.change(within(group).getByLabelText("Note"), { target: { value: "Course rate" } });
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(sent(fetch).agent_commission).toEqual({ percent: "12", note: "Course rate" });
    cleanup();
    fetch.mockClear();
    form({ canEditAgentCommission: true });
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(sent(fetch)).not.toHaveProperty("agent_commission");
  });

  it("asks for the currency of a fixed amount before sending", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    form({ canEditAgentCommission: true });
    fillRequired();
    const group = screen.getByRole("group", { name: "Agent Master commission" });
    fireEvent.click(within(group).getByLabelText("Fixed amount"));
    fireEvent.change(within(group).getByLabelText("Amount"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    expect(screen.getByRole("alert").textContent).toBe("Agent Master commission: Choose the currency.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("checks the rate itself, naming the agent commission, before sending (QA-051-01)", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    form({ canEditAgentCommission: true });
    fillRequired();
    const percent = within(screen.getByRole("group", { name: "Agent Master commission" })).getByLabelText("Percent", { exact: true });
    for (const [value, message] of [
      ["150", "Agent Master commission: The percentage cannot be above 100."],
      ["0", "Agent Master commission: Enter a rate above 0 with at most two decimal places."],
      ["12.345", "Agent Master commission: Enter a rate above 0 with at most two decimal places."],
    ]) {
      fireEvent.change(percent, { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "Save course" }));
      expect(screen.getByRole("alert").textContent).toBe(message);
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  it("prefills an edit, sends only a change, and a cleared rate as null", async () => {
    const fetch = vi.fn(async () => res({ course: course() }));
    vi.stubGlobal("fetch", fetch);
    const editing = course({ agent_commission: { percent: "12.00", amount: null, currency: null, note: "Course rate" } });
    const onSaved = vi.fn();
    form({ canEditAgentCommission: true, course: editing, label: "Edit", onSaved });
    const percent = within(screen.getByRole("group", { name: "Agent Master commission" })).getByLabelText("Percent", { exact: true }) as HTMLInputElement;
    expect(percent.value).toBe("12.00");
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    expect(onSaved).toHaveBeenCalledWith("No changes to save.");
    fireEvent.change(percent, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(sent(fetch)).toEqual({ agent_commission: null });
  });

  it("uses its own ids, so it never clashes with the university card on the same page", () => {
    form({ canEditAgentCommission: true });
    const percent = within(screen.getByRole("group", { name: "Agent Master commission" })).getByLabelText("Percent", { exact: true });
    expect(percent.id).not.toBe("agent-commission-percent");
    expect(percent.id.startsWith("course-new-u1")).toBe(true);
  });

  it("UniversityCourses shows the course's agent commission only when the API sent it", () => {
    const page: CoursePage = { items: [course({ agent_commission: { percent: "12.00", amount: null, currency: null, note: null } }), course({ id: "c2", title: "MBA" })], total: 2, limit: 50, offset: 0, can_edit: false };
    render(<UniversityCourses universityId="u1" page={page} options={null} canSetCommission={false} canEditAgentCommission />);
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(first).getByText("Agent Master commission")).toBeTruthy();
    expect(within(first).getByText("12.00%")).toBeTruthy();
    expect(within(second).queryByText("Agent Master commission")).toBeNull();
  });
});
