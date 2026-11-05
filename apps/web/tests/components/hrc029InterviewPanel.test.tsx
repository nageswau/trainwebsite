import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InterviewerWorkspace from "@/components/InterviewerWorkspace";
import RecruiterInterviewItem from "@/components/RecruiterInterviewItem";
import { experienceText, type MyInterview } from "@/lib/interviewerWorkspace";
import { type PanelMember } from "@/lib/recruiterInterviews";
import { recInterview } from "@/tests/helpers/recruiterInterviews";

// hrc-029 (DEC-SCOPE-405 V6-V12): the recruiter's interview panel (assign, each member's feedback) and the panel member's workspace.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/recruiter/interviews",
  useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let fetchMock: ReturnType<typeof vi.fn>;
let replies: Record<string, () => Response>;
beforeEach(() => {
  replies = {};
  fetchMock = vi.fn((url: string) => {
    const key = Object.keys(replies).find((k) => url.includes(k));
    return Promise.resolve(key ? replies[key]() : res({ detail: "Not found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const member = (over: Partial<PanelMember> = {}): PanelMember => ({ id: "u1", full_name: "Asha Rao", kind: "internal", kind_label: "Internal interviewer", is_lead: true, feedback: null, ...over });

function mine(over: Partial<MyInterview> = {}): MyInterview {
  return {
    id: "i1", code: "INT-000009", round_label: "Technical Round", round_number: 2, scheduled_at: "2026-10-12T05:30:00Z", ends_at: null, mode: "Online",
    platform_label: "Zoom", meeting_url: "https://meet.example.com/x", location: null, phone_details: null, instructions: "Ask about Java", status: "scheduled",
    status_label: "Scheduled", cancel_reason: null, is_lead: true,
    candidate: { code: "CAN-000042", name: "Ravi Kumar", location: "Pune", qualification: "B.Tech", experience_months: 26, current_company: "Acme", skills: ["Java", "SQL"] },
    requirement: { code: "JOB-1", title: "Java Developer" }, company: { name: "Infosys" }, has_resume: true, feedback: null, can_feedback: true,
    feedback_overdue: false, ...over,
  };
}
const page = (items: MyInterview[], counts = { upcoming: items.length, past: 0 }) => res({ items, total: items.length, limit: 20, offset: 0, counts });

describe("helpers", () => {
  it("words experience", () => {
    expect(experienceText(26)).toBe("2 yrs 2 mos");
    expect(experienceText(12)).toBe("1 yr");
    expect(experienceText(0)).toBe("Less than a month");
    expect(experienceText(null)).toBeNull();
  });
});

describe("RecruiterInterviewItem panel (hrc-029 V9)", () => {
  it("lists each member with their own feedback", () => {
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview({ can_assign: true, interviewers: [
      member({ feedback: { attendance: "attended", attendance_label: "Attended", score: 4, recommendation: "yes", recommendation_label: "Recommend", notes: "Good SQL", updated_at: "2026-10-12T08:00:00Z" } }),
      member({ id: "u2", full_name: "Employer Bose", kind: "employer", kind_label: "Employer", is_lead: false }),
    ] })} /></ul>);
    const panel = screen.getByRole("list", { name: "Interview panel of INT-000001" });
    expect(panel.textContent).toContain("Asha Rao (Internal interviewer, lead) — Attended, 4 / 5, Recommend");
    expect(panel.textContent).toContain("Good SQL");
    expect(panel.textContent).toContain("Employer Bose (Employer) — no feedback yet");
    expect(screen.getByRole("button", { name: /Edit panel/ })).toBeTruthy();
  });

  it("hides the panel for a reader with no members", () => {
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview({ can_assign: false, interviewers: [] })} /></ul>);
    expect(screen.queryByText("Interview panel")).toBeNull();
  });

  it("assigns interviewers with a lead and reports the save", async () => {
    replies["interviewer-options"] = () => res({ items: [
      { id: "u1", full_name: "Asha Rao", email: "asha@x.local", kind: "internal", kind_label: "Internal interviewer" },
      { id: "u2", full_name: "Employer Bose", email: "bose@x.local", kind: "employer", kind_label: "Employer" },
    ] });
    replies["/interviewers"] = () => res({ interview: recInterview({ can_assign: true, interviewers: [member()] }) });
    const onChanged = vi.fn();
    render(<ul><RecruiterInterviewItem onChanged={onChanged} interview={recInterview({ can_assign: true, interviewers: [] })} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: /Assign interviewers/ }));
    const form = screen.getByRole("form", { name: "Interview panel for INT-000001" });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /Asha Rao/ }));
    fireEvent.click(within(form).getByRole("radio", { name: /Lead interviewer: Asha Rao/ }));
    fireEvent.click(within(form).getByRole("button", { name: "Save panel" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(put![1].body)).toEqual({ interviewers: [{ user_id: "u1", is_lead: true }] });
    expect(onChanged.mock.calls[0][1]).toContain("Interview panel saved.");
  });

  it("shows the API refusal on the form", async () => {
    replies["interviewer-options"] = () => res({ items: [{ id: "u1", full_name: "Asha Rao", email: "a@x", kind: "internal", kind_label: "Internal interviewer" }] });
    replies["/interviewers"] = () => res({ detail: "An interviewer who has submitted feedback cannot be removed" }, 409);
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview({ can_assign: true, interviewers: [member()] })} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: /Edit panel/ }));
    const form = screen.getByRole("form", { name: "Interview panel for INT-000001" });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /Asha Rao/ }));
    fireEvent.click(within(form).getByRole("button", { name: "Save panel" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("cannot be removed");
  });
});

describe("InterviewerWorkspace (hrc-029 V6/V7)", () => {
  it("shows loading, then the empty state", async () => {
    replies["/interviewer/interviews"] = () => page([]);
    render(<InterviewerWorkspace />);
    expect(screen.getByText("Loading your interviews…")).toBeTruthy();
    expect(await screen.findByText("No interviews are assigned to you yet.")).toBeTruthy();
  });

  it("shows the card with the candidate summary, the resume link and no contact detail", async () => {
    replies["/interviewer/interviews"] = () => page([mine({ feedback_overdue: true })]);
    render(<InterviewerWorkspace />);
    const card = await screen.findByRole("listitem");
    for (const text of ["Ravi Kumar", "CAN-000042", "Java Developer · Infosys", "Technical Round (round 2)", "B.Tech", "2 yrs 2 mos", "Java, SQL", "Lead interviewer", "Feedback overdue", "Ask about Java"]) {
      expect(card.textContent).toContain(text);
    }
    expect(within(card).getByRole("link", { name: /Download resume/ }).getAttribute("href")).toBe("/api/v1/interviewer/interviews/i1/resume");
    expect(screen.getByRole("button", { name: "Upcoming (1)" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("says no resume is shared and that feedback waits for the interview time", async () => {
    replies["/interviewer/interviews"] = () => page([mine({ has_resume: false, can_feedback: false, scheduled_at: "2099-01-01T05:30:00Z" })]);
    render(<InterviewerWorkspace />);
    expect(await screen.findByText("No resume shared")).toBeTruthy();
    expect(screen.getByText("Feedback opens once the interview time has passed.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Submit feedback/ })).toBeNull();
  });

  it("requires a score and a recommendation when attended, then saves", async () => {
    replies["/interviewer/interviews?"] = () => page([mine()]);
    replies["/feedback"] = () => res(mine({ feedback: { attendance: "attended", attendance_label: "Attended", score: 5, recommendation: "strong_yes",
      recommendation_label: "Strongly recommend", notes: "Great", updated_at: "2026-10-12T09:00:00Z" } }));
    render(<InterviewerWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: /Submit feedback/ }));
    const form = screen.getByRole("form", { name: "Feedback for INT-000009" });
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    expect(within(form).getByText("Choose a score", { selector: "p" })).toBeTruthy();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
    fireEvent.change(within(form).getByLabelText("Score (required)"), { target: { value: "5" } });
    fireEvent.change(within(form).getByLabelText("Recommendation (required)"), { target: { value: "strong_yes" } });
    fireEvent.change(within(form).getByLabelText("Notes"), { target: { value: "  Great " } });
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    expect(await screen.findByText("Feedback saved for Ravi Kumar.")).toBeTruthy();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(put![1].body)).toEqual({ attendance: "attended", score: 5, recommendation: "strong_yes", notes: "Great" });
    expect(screen.getByRole("list", { name: "Your feedback for INT-000009" }).textContent).toContain("Strongly recommend");
  });

  it("sends a no-show without a score", async () => {
    replies["/interviewer/interviews?"] = () => page([mine()]);
    replies["/feedback"] = () => res(mine({ feedback: { attendance: "no_show", attendance_label: "No-show", score: null, recommendation: null, recommendation_label: null, notes: null, updated_at: "2026-10-12T09:00:00Z" } }));
    render(<InterviewerWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: /Submit feedback/ }));
    const form = screen.getByRole("form", { name: "Feedback for INT-000009" });
    fireEvent.click(within(form).getByRole("radio", { name: "No-show" }));
    expect((within(form).getByLabelText("Score") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.click(within(form).getByRole("button", { name: "Save feedback" }));
    await screen.findByText("Feedback saved for Ravi Kumar.");
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(put![1].body)).toEqual({ attendance: "no_show", score: null, recommendation: null, notes: null });
  });

  it("shows a load failure with a retry, and the session-ended link on 401", async () => {
    replies["/interviewer/interviews"] = () => res({ detail: "boom" }, 500);
    render(<InterviewerWorkspace />);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    replies["/interviewer/interviews"] = () => page([]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No interviews are assigned to you yet.")).toBeTruthy();
    cleanup();
    replies["/interviewer/interviews"] = () => res({ detail: "Not authenticated" }, 401);
    render(<InterviewerWorkspace />);
    expect(await screen.findByRole("link", { name: "Return to login" })).toBeTruthy();
  });

  it("switches to the Past view", async () => {
    replies["/interviewer/interviews"] = () => page([], { upcoming: 0, past: 3 });
    render(<InterviewerWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Past (3)" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("view=past"))).toBe(true));
    expect(await screen.findByText("No past interviews.")).toBeTruthy();
  });
});
