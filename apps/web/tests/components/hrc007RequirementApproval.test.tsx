import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementDetail from "@/components/RecruiterRequirementDetail";
import RequirementApprovalQueue from "@/components/RequirementApprovalQueue";
import type { ApprovalRow, ApprovalSettings, Requirement } from "@/lib/recruiterRequirements";

// hrc-007 (DEC-SCOPE-380 A6/A8/A9): sending a requirement for approval, deciding one, and the approver's queue. The server decides every
// rule; these check what is sent and how the answer is shown.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }), usePathname: () => "/x" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const approval = (over = {}) => ({ required: false, submitted_by: null, submitted_at: null, can_submit: false, can_decide: false, ...over });
const requirement = (over: Partial<Requirement> = {}) =>
  ({
    id: "R1", code: "REQ-0001", title: "Java Dev", company: { id: "C1", code: "CO-1", name: "Acme" }, location: "Pune", status: "new", status_label: "New",
    phase: "draft", phase_label: "Draft", source: "recruiter", priority: null, vacancies: 2, closes_on: null, requirement_date: null, deadline_state: null,
    assigned_recruiter: null, permissions: { can_edit: true, can_change_status: true, can_reassign: false, can_view_matches: false }, description: "Build APIs",
    department: null, job_category: null, qualification: null, experience_min_months: null, experience_max_months: null, salary_min: null, salary_max: null,
    work_mode: null, shift: null, employment_type: null, joining_requirement: null, skills: [], joined_count: 0, allowed_statuses: [], status_history: [],
    created_by: null, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-04T04:00:00Z", approval: approval(),
    visibility: { key: "public", label: "Public website", segment_pool: null, can_change: false }, ...over,
  }) as Requirement;
const row = (over: Partial<ApprovalRow> = {}) =>
  ({ ...requirement({ status: "pending_approval", status_label: "Pending Approval", source: "employer" }), submitted_by: { id: "e1", full_name: "Emp Loyer" },
    submitted_at: "2026-11-04T05:00:00Z", can_decide: true, ...over }) as ApprovalRow;
const settings: ApprovalSettings = { settings: { employer: true, recruiter: false, legacy: false }, can_edit: false };

let posts: { url: string; method: string; body: Record<string, unknown> }[];
let replies: Response[];

beforeEach(() => {
  posts = [];
  replies = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") {
      posts.push({ url, method: init.method, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(replies.shift()!);
    }
    return Promise.resolve(res({ items: [], total: 0, versions: [] }));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-007 requirement detail approval", () => {
  it("submits a draft for approval with the note and shows the pending state", async () => {
    const pending = requirement({ status: "pending_approval", status_label: "Pending Approval",
      approval: approval({ required: false, submitted_by: { id: "u1", full_name: "Rita Recruiter" }, submitted_at: "2026-11-04T05:00:00Z" }) });
    replies = [res({ requirement: pending })];
    render(<RecruiterRequirementDetail initial={requirement({ approval: approval({ required: true, can_submit: true }) })} initialJd={null} />);
    fireEvent.change(screen.getByLabelText("Note for the approver (optional)"), { target: { value: " Ready " } });
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(screen.getByText(/Sent for approval\. It opens once/)).toBeTruthy());
    expect(posts[0]).toMatchObject({ url: "/api/v1/recruiter/requirements/R1/submit", method: "POST", body: { note: "Ready" } });
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
    expect(screen.getByText(/Waiting for an approver/)).toBeTruthy();
    expect(screen.getByText(/by Rita Recruiter/)).toBeTruthy();
  });

  it("offers no submit button when the job needs no approval", () => {
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
  });

  it("shows the server's refusal", async () => {
    replies = [res({ detail: "This requirement does not need approval" }, 409)];
    render(<RecruiterRequirementDetail initial={requirement({ approval: approval({ required: true, can_submit: true }) })} initialJd={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(screen.getByText("This requirement does not need approval")).toBeTruthy());
  });
});

describe("hrc-007 approval queue", () => {
  it("lists a pending job; a reject needs a reason, then the row leaves the list", async () => {
    replies = [res({ requirement: requirement() })];
    render(<RequirementApprovalQueue rows={[row()]} total={1} settings={settings} />);
    expect(screen.getByText("Waiting for approval (1)")).toBeTruthy();
    expect(screen.getByText("Employer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("alert").textContent).toContain("Give a reason");
    expect(posts).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Note, or the reason when rejecting"), { target: { value: "Salary missing" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(screen.getByText("REQ-0001 rejected and returned to draft.")).toBeTruthy());
    expect(posts[0]).toMatchObject({ url: "/api/v1/recruiter/requirements/R1/reject", body: { reason: "Salary missing" } });
    expect(screen.getByText("No job requirements are waiting for approval.")).toBeTruthy();
    expect(screen.getByText("Waiting for approval (0)")).toBeTruthy();
  });

  it("approves with an optional note", async () => {
    replies = [res({ requirement: requirement({ status: "requirement_received" }) })];
    render(<RequirementApprovalQueue rows={[row()]} total={1} settings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByText("REQ-0001 approved. It is now open.")).toBeTruthy());
    expect(posts[0]).toMatchObject({ url: "/api/v1/recruiter/requirements/R1/approve", body: {} });
  });

  it("explains why one's own job cannot be decided, and shows the server's error", async () => {
    replies = [res({ detail: "You cannot approve or reject your own job requirement" }, 403)];
    render(<RequirementApprovalQueue rows={[row({ id: "R2", code: "REQ-0002", can_decide: false }), row()]} total={2} settings={settings} />);
    expect(screen.getByText(/your own job requirement, so another approver/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByText("You cannot approve or reject your own job requirement")).toBeTruthy());
  });

  it("lets only a super admin change which sources need approval", async () => {
    const { unmount } = render(<RequirementApprovalQueue rows={[]} total={0} settings={settings} />);
    expect((screen.getByLabelText("Employer jobs") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Only a super admin can change these settings.")).toBeTruthy();
    unmount();
    replies = [res({ settings: { employer: true, recruiter: true, legacy: false }, can_edit: true })];
    render(<RequirementApprovalQueue rows={[]} total={0} settings={{ ...settings, can_edit: true }} />);
    fireEvent.click(screen.getByLabelText("Recruiter jobs"));
    await waitFor(() => expect(screen.getByText("Recruiter jobs now need approval.")).toBeTruthy());
    expect(posts[0]).toMatchObject({ url: "/api/v1/recruiter/requirement-approvals/settings", method: "PUT", body: { recruiter: true } });
    expect((screen.getByLabelText("Recruiter jobs") as HTMLInputElement).checked).toBe(true);
  });

  it("QA-01: a setting ticks at once, and goes back when the save fails", async () => {
    let fail!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { fail = resolve; })));
    render(<RequirementApprovalQueue rows={[]} total={0} settings={{ ...settings, can_edit: true }} />);
    const box = screen.getByLabelText("Recruiter jobs") as HTMLInputElement;
    fireEvent.click(box);
    expect(box.checked).toBe(true); // before the server answers
    fail(res({ detail: "Only a super admin can change the approval settings" }, 403));
    await waitFor(() => expect(screen.getByText("Only a super admin can change the approval settings")).toBeTruthy());
    expect(box.checked).toBe(false);
  });
});
