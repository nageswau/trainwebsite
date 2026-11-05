import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MyResultsCard from "@/components/MyResultsCard";
import RecruiterInterviewItem from "@/components/RecruiterInterviewItem";
import ResultApprovalQueue from "@/components/ResultApprovalQueue";
import { type InterviewResult, type MyResult, parseOffset, queueUrl, type ResultQueue, type ResultRow } from "@/lib/interviewResults";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { recInterview } from "@/tests/helpers/recruiterInterviews";

// hrc-030 (DEC-SCOPE-409 R9-R13): the candidate's published results, the approver's queue and the recruiter's view of the result.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/it/hr-manager/results",
  useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const result = (over: Partial<InterviewResult> = {}): InterviewResult => ({
  id: "r1", outcome: "selected", outcome_label: "Selected", is_final: true, state: "pending_approval", state_label: "Waiting for approval",
  candidate_message: "Congratulations! You have been selected for Java Developer at Infosys.", release_mode: null, released_at: null, ...over,
});
const row = (over: Partial<ResultRow> = {}): ResultRow => ({
  ...result(), interview: { id: "i1", code: "INT-000001", round: "Final Round", scheduled_at: "2026-10-12T05:30:00Z" },
  candidate: { id: "c1", code: "CAN-000042", name: "Ravi Kumar" }, requirement: { id: "j1", code: "JOB-1", title: "Java Developer" },
  company: { id: "co1", name: "Infosys" }, decided_by: { id: "u1", full_name: "Rec One" }, decided_at: "2026-10-12T08:00:00Z", can_release: true, ...over,
});
const queue = (items: ResultRow[]): ResultQueue => ({ items, total: items.length, limit: 50, offset: 0, counts: { pending_approval: items.length, released: 3 } });
const settings = { auto_release: false, can_edit: false };

describe("MyResultsCard", () => {
  it("shows the published results with their message", async () => {
    const mine: MyResult = { id: "r1", round: "Final Round", role: "Java Developer", company: "Infosys", outcome: "selected", outcome_label: "Selected",
      message: "Well done", released_at: "2026-10-12T08:00:00Z" };
    fetchMock.mockResolvedValue(res({ items: [mine] }));
    render(<MyResultsCard />);
    expect(screen.getByRole("status").textContent).toBe("Loading results…");
    const list = await screen.findByRole("list", { name: "My results" });
    expect(list.textContent).toContain("Infosys");
    expect(list.textContent).toContain("Selected");
    expect(list.textContent).toContain("Well done");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/candidate/results");
  });

  it("says when there is nothing yet", async () => {
    fetchMock.mockResolvedValue(res({ items: [] }));
    render(<MyResultsCard />);
    expect(await screen.findByText(/No interview results yet/)).toBeTruthy();
  });

  it("offers a retry after a failure", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res({ items: [] }));
    render(<MyResultsCard />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load your results.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/No interview results yet/)).toBeTruthy();
  });
});

describe("ResultApprovalQueue", () => {
  it("publishes with the edited message and takes the row off the list", async () => {
    fetchMock.mockResolvedValue(res(result({ state: "released" })));
    render(<ResultApprovalQueue state="pending_approval" page={queue([row()])} settings={settings} />);
    expect(screen.getByRole("link", { name: "Waiting for approval (1)" }).getAttribute("aria-current")).toBe("page");
    const box = screen.getByLabelText("Message to the candidate") as HTMLTextAreaElement;
    expect(box.value).toContain("Congratulations");
    fireEvent.change(box, { target: { value: "  Welcome aboard  " } });
    fireEvent.click(screen.getByRole("button", { name: "Publish result" }));
    await waitFor(() => expect(screen.getByText("No interview results are waiting for approval.")).toBeTruthy());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/recruiter/interview-results/r1/release");
    expect(JSON.parse(init.body)).toEqual({ candidate_message: "Welcome aboard" });
    expect(screen.getByText("Result published to Ravi Kumar (CAN-000042).")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Published (4)" })).toBeTruthy();
  });

  it("keeps the row and shows the server's refusal", async () => {
    fetchMock.mockResolvedValue(res({ detail: "This result is already published" }, 409));
    render(<ResultApprovalQueue state="pending_approval" page={queue([row()])} settings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "Publish result" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already published");
    expect(screen.getByRole("button", { name: "Publish result" })).toBeTruthy();
  });

  it("explains an own decision and shows no Publish button", () => {
    render(<ResultApprovalQueue state="pending_approval" page={queue([row({ can_release: false })])} settings={settings} />);
    expect(screen.queryByRole("button", { name: "Publish result" })).toBeNull();
    expect(screen.getByText(/another approver must publish it/)).toBeTruthy();
  });

  it("lists published results read-only and the setting is locked for a non-super-admin", () => {
    render(<ResultApprovalQueue state="released" page={queue([row({ state: "released", release_mode: "auto", released_at: "2026-10-13T08:00:00Z" })])} settings={settings} />);
    const item = screen.getByRole("listitem");
    expect(within(item).getByText(/Published automatically on/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Publish result" })).toBeNull();
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Only a super admin can change this setting.")).toBeTruthy();
  });

  it("lets a super admin switch auto-release on", async () => {
    fetchMock.mockResolvedValue(res({ auto_release: true, can_edit: true }));
    render(<ResultApprovalQueue state="pending_approval" page={queue([])} settings={{ auto_release: false, can_edit: true }} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(await screen.findByText("Results are now published automatically.")).toBeTruthy();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ auto_release: true });
  });
});

describe("RecruiterInterviewItem result line (R10)", () => {
  it("says the candidate has not been told yet", () => {
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview({ result_release: result() })} /></ul>);
    expect(screen.getByText(/waiting for approval before the candidate sees it/)).toBeTruthy();
  });

  it("says when it was published", () => {
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview({ result_release: result({ state: "released", release_mode: "approval", released_at: "2026-10-13T08:00:00Z" }) })} /></ul>);
    expect(screen.getByText(/published on/)).toBeTruthy();
  });

  it("shows nothing without a result", () => {
    render(<ul><RecruiterInterviewItem onChanged={vi.fn()} interview={recInterview()} /></ul>);
    expect(screen.queryByText(/Result for the candidate/)).toBeNull();
  });
});

describe("ResultApprovalQueue paging (QA-02)", () => {
  it("links the next and the previous page of a long list, keeping the tab", () => {
    const page = { ...queue([row()]), total: 120, offset: 50 };
    render(<ResultApprovalQueue state="pending_approval" page={page} settings={settings} />);
    expect(screen.getByText("Showing 51–51 of 120.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/it/hr-manager/results?state=pending_approval&offset=0");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/it/hr-manager/results?state=pending_approval&offset=100");
  });

  it("shows no paging when everything fits", () => {
    render(<ResultApprovalQueue state="pending_approval" page={queue([row()])} settings={settings} />);
    expect(screen.queryByRole("link", { name: "Next page" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Previous page" })).toBeNull();
  });

  it("asks the API for the requested page", () => {
    expect(queueUrl("released", 100)).toBe("/api/v1/recruiter/interview-results?state=released&limit=50&offset=100");
    expect(parseOffset("abc")).toBe(0);
    expect(parseOffset("-5")).toBe(0);
    expect(parseOffset("150")).toBe(150);
  });
});

describe("Result approvals in the super admin menu (QA-01)", () => {
  it("links the page, where only a super admin can change the release setting", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Interview Result Approvals", href: "/it/hr-manager/results" });
  });
});
