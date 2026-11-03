import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminHrReviews from "@/components/AdminHrReviews";
import HrReviewCard from "@/components/HrReviewCard";
import StudentHrReviewCard from "@/components/StudentHrReviewCard";
import { ADMIN_RULES_API, hrTaskUrl, MY_REVIEW_API, ownerUrl, ruleUrl, type HrReviewSummary, type HrReviewTask, type HrRules } from "@/lib/hrReviews";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const summary = (extra: Partial<HrReviewSummary> = {}): HrReviewSummary => ({
  id: "t1", student: { id: "s1", full_name: "Asha Rao", student_code: "EDU-1" }, owner: { id: "h1", full_name: "Priya HR", active: true },
  stage: "resume_received", stage_label: "Resume received", resume_version: 2, screening_date: null, assigned_at: "2026-11-02T10:00:00Z",
  closed_at: null, updated_at: "2026-11-02T10:00:00Z", ...extra,
});
const task = (extra: Partial<HrReviewTask> = {}): HrReviewTask => ({
  ...summary(), role_preferences: null, skill_gap_notes: null, checklist: [],
  history: [{ from_stage: null, to_stage: "resume_received", reason: "upload", actor: null, created_at: "2026-11-02T10:00:00Z" }], ...extra,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HrReviewCard (itc-027)", () => {
  it("saves the stage, fields and checklist the owner changed and shows the saved state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(task()))
      .mockResolvedValueOnce(res(task({ stage: "changes_requested", stage_label: "Changes requested", checklist: ["skills"], skill_gap_notes: "SQL" })));
    vi.stubGlobal("fetch", fetchMock);
    render(<HrReviewCard studentId="s1" />);
    const stage = await screen.findByLabelText("Stage");
    fireEvent.change(stage, { target: { value: "changes_requested" } });
    fireEvent.click(screen.getByLabelText("Skills match the course"));
    fireEvent.change(screen.getByLabelText(/Skill-gap notes/), { target: { value: "SQL" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));
    expect(await screen.findByText("Review saved.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe(hrTaskUrl("s1"));
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ stage: "changes_requested", screening_date: null, role_preferences: "", skill_gap_notes: "SQL", checklist: ["skills"] });
    expect(screen.getByLabelText("Stage")).toHaveValue("changes_requested");
  });

  it("says when no task is assigned to this HR user (404)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Review task not found" }, 404)));
    render(<HrReviewCard studentId="s1" />);
    expect(await screen.findByText(/No resume review of this student is assigned to you/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save review" })).not.toBeInTheDocument();
  });

  it("shows a closed review read-only, with the server's message on a failed save", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(task({ stage: "completed", stage_label: "Completed", closed_at: "2026-11-02T11:00:00Z" }))));
    render(<HrReviewCard studentId="s1" />);
    expect(await screen.findByText(/This review is closed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save review" })).not.toBeInTheDocument();
  });

  it("keeps the form and shows the error when a save fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(task())).mockResolvedValueOnce(res({ detail: "This review is closed." }, 409)));
    render(<HrReviewCard studentId="s1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Save review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This review is closed.");
    expect(screen.getByRole("button", { name: "Save review" })).toBeEnabled();
  });
});

describe("StudentHrReviewCard (itc-027)", () => {
  it("shows only the safe label and the action", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ status: { label: "Action required: update your resume", action: "Upload an updated resume.", updated_at: "2026-11-02T10:00:00Z" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentHrReviewCard />);
    expect(await screen.findByText("Action required: update your resume")).toBeInTheDocument();
    expect(screen.getByText("Upload an updated resume.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(MY_REVIEW_API, expect.anything());
  });

  it("explains the empty state before any shared resume", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ status: null })));
    render(<StudentHrReviewCard />);
    expect(await screen.findByText(/Share a resume with HR/)).toBeInTheDocument();
  });
});

describe("AdminHrReviews (itc-027)", () => {
  const rules: HrRules = {
    programs: [{ program_id: "p1", program: "Python", active: true, hr_user: null }],
    hr_users: [{ id: "h1", full_name: "Priya HR" }, { id: "h2", full_name: "Ravi HR" }],
  };

  it("reassigns a task and sets a programme rule", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === ADMIN_RULES_API) return Promise.resolve(res(rules));
      if (url === ownerUrl("t1")) return Promise.resolve(res(summary({ owner: { id: "h2", full_name: "Ravi HR", active: true } })));
      if (url === ruleUrl("p1")) return Promise.resolve(res({ ...rules.programs[0], hr_user: { id: "h2", full_name: "Ravi HR", active: true } }));
      void init;
      return Promise.resolve(res({ items: [summary({ owner: { id: "h1", full_name: "Priya HR", active: false } })], total: 1, limit: 25, offset: 0 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminHrReviews />);
    const row = (await screen.findByRole("row", { name: /Asha Rao/ }));
    expect(within(row).getByText(/deactivated/i)).toBeInTheDocument();
    // QA27-01/02: on phones the stacked labels stay short and the Student ID has its own cell (no mid-code wrap)
    expect(within(row).getByText("EDU-1").closest("td")).toHaveAttribute("data-label", "Student ID");
    expect(within(row).getByRole("button", { name: "Assign" }).closest("td")).toHaveAttribute("data-label", "Assign");
    fireEvent.change(within(row).getByLabelText("Reassign Asha Rao"), { target: { value: "h2" } });
    fireEvent.click(within(row).getByRole("button", { name: "Assign" }));
    expect(await screen.findByText("Asha Rao's review is now with Ravi HR.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("HR reviewer for Python"), { target: { value: "h2" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(ruleUrl("p1"), expect.objectContaining({ method: "PUT", body: JSON.stringify({ hr_user_id: "h2" }) })));
    expect(await screen.findByText("Python: new reviews go to Ravi HR.")).toBeInTheDocument();
  });
});
