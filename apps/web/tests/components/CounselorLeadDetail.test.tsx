import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadDetail from "@/components/CounselorLeadDetail";
import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";
import type { CounselorLeadDetail as Detail } from "@/lib/leadHandover";

// ccrm-012: the leads panel keeps its filters in the URL.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/overseas/counselor/leads", useSearchParams: () => new URLSearchParams() }));

// tel-018 (spec §4; T19, T20; HO1, HO4): the counselor's lead -- return with a reason, link a suggested or searched student, unlink.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const detail = (over: Partial<Detail> = {}): Detail => ({
  id: "L1", lead_code: "LD-000042", name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", whatsapp_number: null, city: null,
  state: null, qualification: null, passing_year: null, institution: null, division: "it", subject: "Python", status: "counselling_completed",
  status_label: "Counselling Completed", source: "website", priority: "warm", created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z",
  product: null, campaign: null, telecaller: { id: "t1", full_name: "Tara Caller" }, counselor: { id: "c1", full_name: "Cara Counselor" },
  converted_user: null, message: "Hello", milestones: { student: null, items: [] }, next_action: null, next_action_due: null, next_action_overdue: false,
  permissions: { return: true, link: true, unlink: false, stage: true, follow_up: true, convert: false, activity: true }, whatsapp_to: "919876543210", ...over,
});
const closedPermissions = { return: true, link: false, unlink: false, stage: false, follow_up: false, convert: false, activity: false };
const asha = { id: "s1", full_name: "Asha Rao", email: "asha@example.com", phone: null, linked_elsewhere: false };
const taken = { id: "s2", full_name: "Asha R", email: "asha.r@example.com", phone: null, linked_elsewhere: true };
const linked = detail({
  status: "application_enrollment", status_label: "Application/Enrollment", converted_user: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" },
  milestones: { student: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" }, items: [] },
  permissions: { return: false, link: false, unlink: true, stage: true, follow_up: true, convert: false, activity: true },
});
const followUp = {
  id: "F1", due_at: "2026-10-30T05:30:00Z", reason: "waiting_documents", notes: null, next_action: "Collect transcripts", status: "open", overdue: false,
  lead: { id: "L1", lead_code: "LD-000042", name: "Asha Rao", priority: "warm", status: "counselling_completed", status_label: "Counselling Completed", product: null, telecaller: null },
  created_by: { id: "c1", full_name: "Cara Counselor" }, created_at: "2026-10-22T05:00:00Z", completed_at: null, completed_by: null, cancelled_at: null,
  cancel_reason: null, can_change: true,
};

let fetchMock: ReturnType<typeof vi.fn>;
let reply: Record<string, () => Response>;
beforeEach(() => {
  reply = {
    "POST /return": () => res(detail({ status: "follow_up", counselor: null })),
    "POST /student-link": () => res(linked),
    "DELETE /student-link": () => res(detail()),
  };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const tail = url.replace("/api/v1/counselor/leads/L1", "");
    if (reply[`${method} ${tail}`]) return Promise.resolve(reply[`${method} ${tail}`]());
    if (tail === "/link-suggestions") return Promise.resolve(res({ items: [asha] }));
    if (tail.startsWith("/link-suggestions?q=")) return Promise.resolve(res({ items: [taken] }));
    if (["/timeline", "/notes", "/follow-ups", "/calls", "/messages", "/meetings"].some((t) => tail.startsWith(t))) return Promise.resolve(res(pageOf([])));
    if (url.startsWith("/api/v1/counselor/leads?")) return Promise.resolve(res(pageOf([detail()])));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const body = (method: string, tail: string) => {
  const call = fetchMock.mock.calls.find(([u, i]) => (i?.method ?? "GET") === method && u === `/api/v1/counselor/leads/L1${tail}`);
  return call?.[1]?.body ? JSON.parse(String(call[1].body)) : call ? {} : undefined;
};

describe("CounselorLeadDetail", () => {
  it("returns the lead with a reason and then offers no further action", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Return to telecaller" }));
    fireEvent.click(screen.getByRole("button", { name: "Return lead" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a reason for returning the lead.");
    fireEvent.change(screen.getByLabelText("Reason for returning"), { target: { value: "Needs fee talk" } });
    fireEvent.click(screen.getByRole("button", { name: "Return lead" }));
    expect(await screen.findByText("Lead returned to the telecaller.")).toBeInTheDocument();
    expect(body("POST", "/return")).toEqual({ reason: "Needs fee talk" });
    expect(screen.queryByRole("button", { name: "Return to telecaller" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Link / })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to my leads" })).toHaveAttribute("href", "/it/counselor/leads");
  });

  it("shows the suggested match, links it after a confirm, then offers unlink", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Link Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, link" }));
    expect(await screen.findByText("Student linked.")).toBeInTheDocument();
    expect(body("POST", "/student-link")).toEqual({ student_id: "s1" });
    expect(screen.getByText(/Stage:/)).toHaveTextContent("Application/Enrollment");
    fireEvent.click(screen.getByRole("button", { name: "Unlink student" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, unlink" }));
    expect(await screen.findByText("Student unlinked.")).toBeInTheDocument();
    expect(body("DELETE", "/student-link")).toEqual({});
  });

  it("searches students and marks one already linked elsewhere", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    await screen.findByRole("button", { name: "Link Asha Rao" });
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "as" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter at least 3 characters.");
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "asha.r" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Already linked to another lead/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Link Asha R" })).toBeNull();
  });

  it("shows a refusal from the API in place", async () => {
    reply["POST /student-link"] = () => res({ detail: "This student is already linked to another lead" }, 409);
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Link Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, link" }));
    expect(await screen.findByText("This student is already linked to another lead")).toBeInTheDocument();
  });

  // ccrm-003 (DEC-SCOPE-243): next action, stage moves and follow-ups on the counselor's lead
  it("asks for a next action when none is set and saves one", async () => {
    reply["PUT /next-action"] = () => res(detail({ next_action: "Send the shortlist", next_action_due: "2026-10-30" }));
    render(<CounselorLeadDetail initial={detail()} />);
    expect(screen.getByText("No next action set. Add one before moving the lead to an open stage.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set next action" }));
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add the next action and its due date.");
    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "  Send the shortlist " } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-10-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    expect(await screen.findByText("Next action saved.")).toBeInTheDocument();
    expect(body("PUT", "/next-action")).toEqual({ next_action: "Send the shortlist", next_action_due: "2026-10-30" });
    expect(screen.getByText("Send the shortlist")).toBeInTheDocument();
  });

  it("marks an overdue next action", () => {
    render(<CounselorLeadDetail initial={detail({ next_action: "Call the parents", next_action_due: "2026-10-01", next_action_overdue: true })} />);
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit next action" })).toBeInTheDocument();
  });

  it("moves the stage through the counselor route with only the CC8 targets", async () => {
    reply["POST /stage"] = () => res({ id: "L1", status: "qualified", status_label: "Qualified", stage_changed_at: "2026-10-22T06:00:00Z", next_action: "Call", next_action_due: "2026-10-30" });
    render(<CounselorLeadDetail initial={detail({ status: "follow_up", status_label: "Follow-up", next_action: "Call", next_action_due: "2026-10-30" })} />);
    fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
    const options = Array.from(screen.getByLabelText("New stage for Asha Rao").querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toEqual(["Choose a stage", "Qualified", "Counselling Scheduled", "Counselling Completed", "Not Interested", "Not Eligible", "Lost"]);
    fireEvent.change(screen.getByLabelText("New stage for Asha Rao"), { target: { value: "qualified" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Stage updated.")).toBeInTheDocument();
    expect(body("POST", "/stage")).toEqual({ to_stage: "qualified" });
    expect(screen.getByText(/Stage:/)).toHaveTextContent("Qualified");
  });

  it("shows the API's next-action refusal on a stage move", async () => {
    reply["POST /stage"] = () => res({ detail: [{ loc: ["body", "next_action"], msg: "Value error, Set a next action and its due date first" }] }, 422);
    render(<CounselorLeadDetail initial={detail({ status: "follow_up", status_label: "Follow-up" })} />);
    fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
    fireEvent.change(screen.getByLabelText("New stage for Asha Rao"), { target: { value: "qualified" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Set a next action and its due date first")).toBeInTheDocument();
  });

  it("lists the lead's follow-ups from the counselor route and adds one without the stage checkbox", async () => {
    reply["GET /follow-ups?limit=50"] = () => res(pageOf([followUp]));
    reply["POST /follow-ups"] = () => res({ ...followUp, id: "F2" }, 201);
    render(<CounselorLeadDetail initial={detail()} />);
    expect(await screen.findByText("Collect transcripts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    expect(screen.queryByLabelText("Also move the lead to Follow-up")).toBeNull();
    fireEvent.change(screen.getByLabelText("Due date and time (IST, required)"), { target: { value: "2030-01-01T10:00" } });
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "fee_details" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add follow-up" }).at(-1)!);
    expect(await screen.findByText("Follow-up added.")).toBeInTheDocument();
    expect(body("POST", "/follow-ups")).toMatchObject({ reason: "fee_details", move_to_follow_up: false });
  });

  it("completes a follow-up through the counselor route", async () => {
    reply["GET /follow-ups?limit=50"] = () => res(pageOf([followUp]));
    fetchMock.mockImplementation(((original) => (url: string, init?: RequestInit) =>
      url === "/api/v1/counselor/follow-ups/F1/complete" ? Promise.resolve(res({ ...followUp, status: "done" })) : original(url, init))(fetchMock.getMockImplementation()!));
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Done" }));
    expect(await screen.findByText("Marked done.")).toBeInTheDocument();
  });

  it("a closed lead offers no stage move, next action or new follow-up", async () => {
    render(<CounselorLeadDetail initial={detail({ status: "lost", status_label: "Lost", permissions: closedPermissions })} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const name of ["Change stage for Asha Rao", "Set next action", "Add follow-up"]) expect(screen.queryByRole("button", { name })).toBeNull();
    expect(screen.getByText("No next action.")).toBeInTheDocument(); // QA-04: no prompt to act on a closed lead
    expect(screen.queryByText(/Add one before moving/)).toBeNull();
  });

  it("confirms a closing move even though the stage control goes away (QA-03), replacing the last notice (QA-02)", async () => {
    const closed = detail({ status: "lost", status_label: "Lost", next_action: "Call", next_action_due: "2026-10-30", permissions: closedPermissions });
    reply["PUT /next-action"] = () => res(detail({ next_action: "Call", next_action_due: "2026-10-30" }));
    reply["POST /stage"] = () => res({ id: "L1", status: "lost", status_label: "Lost", stage_changed_at: "2026-10-22T06:00:00Z", next_action: "Call", next_action_due: "2026-10-30" });
    reply["GET "] = () => res(closed);
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Set next action" }));
    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "Call" } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-10-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    expect(await screen.findByText("Next action saved.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
    fireEvent.change(screen.getByLabelText("New stage for Asha Rao"), { target: { value: "lost" } });
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Chose another agency" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Stage updated.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Change stage for Asha Rao" })).toBeNull());
    expect(screen.getByText("Stage updated.")).toBeInTheDocument();
    expect(screen.queryByText("Next action saved.")).toBeNull();
  });

  it("puts the counselor's actions before the student link (QA-01)", () => {
    render(<CounselorLeadDetail initial={detail()} />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.indexOf("Next action")).toBeLessThan(headings.indexOf("Student account"));
    expect(headings.indexOf("Follow-ups")).toBeLessThan(headings.indexOf("Student account"));
  });

  it("a converted lead offers neither return, link nor unlink", async () => {
    render(<CounselorLeadDetail initial={{ ...linked, status: "converted", status_label: "Converted", permissions: { return: false, link: false, unlink: false, stage: false, follow_up: false, convert: false, activity: false } }} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const name of ["Return to telecaller", "Unlink student"]) expect(screen.queryByRole("button", { name })).toBeNull();
    expect(screen.getAllByText("Converted").length).toBeGreaterThan(0);
  });
});

// ccrm-008 (DEC-SCOPE-252): one-step conversion to a new overseas student, prefilled from the lead.
describe("CounselorLeadDetail convert", () => {
  const overseas = (over: Partial<Detail> = {}) =>
    detail({ division: "overseas", status: "qualified", status_label: "Qualified", permissions: { return: true, link: true, unlink: false, stage: true, follow_up: true, convert: true, activity: true }, ...over });
  const student = { id: "S9", full_name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", student_code: "AB12CD34", setup: "pending_setup" };

  it("converts with the lead's details prefilled and links to the new student's profile", async () => {
    reply["POST /convert"] = () => res({ student, lead: { ...linked, division: "overseas", converted_user: { id: "S9", full_name: "Asha Rao", email: "asha@example.com" } }, email_status: "sent", expires_at: "2026-10-27T00:00:00Z" }, 201);
    render(<CounselorLeadDetail initial={overseas()} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to student" }));
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha Rao");
    expect(screen.getByLabelText("Email")).toHaveValue("asha@example.com");
    expect(screen.getByLabelText("Phone (optional)")).toHaveValue("+91 98765 43210");
    fireEvent.click(screen.getByRole("button", { name: "Create student account" }));
    expect(await screen.findByText(/Student account created for Asha Rao\. A set-password link was emailed to asha@example\.com\./)).toBeInTheDocument();
    expect(body("POST", "/convert")).toEqual({ full_name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210" });
    expect(screen.getByRole("link", { name: "Open the student's profile" })).toHaveAttribute("href", "/overseas/counselor/students/S9/profile");
    expect(screen.getByText(/Linked to/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convert to student" })).toBeNull();
  });

  it("keeps the entry and points to the link list when the student already exists", async () => {
    reply["POST /convert"] = () => res({ detail: "A student account already has this email or mobile. Link the existing student instead." }, 409);
    render(<CounselorLeadDetail initial={overseas()} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to student" }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha R. Rao" } });
    fireEvent.click(screen.getByRole("button", { name: "Create student account" }));
    expect(await screen.findByText(/Link the existing student instead/)).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha R. Rao");
    expect(screen.getByRole("button", { name: "Link Asha Rao" })).toBeInTheDocument();
  });

  it("asks for an email when the lead has none (a phone-only lead)", async () => {
    render(<CounselorLeadDetail initial={overseas({ email: null })} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to student" }));
    expect(screen.getByLabelText("Email")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Create student account" }));
    expect(await screen.findByText("Add the student's name and email.")).toBeInTheDocument();
    expect(body("POST", "/convert")).toBeUndefined();
  });

  it("explains why an overseas lead before Qualified cannot be converted yet", () => {
    render(<CounselorLeadDetail initial={overseas({ status: "contacted", status_label: "Contacted", permissions: { return: true, link: true, unlink: false, stage: true, follow_up: true, convert: false, activity: true } })} />);
    expect(screen.queryByRole("button", { name: "Convert to student" })).toBeNull();
    expect(screen.getByText("Move the lead to Qualified to convert it to a new student.")).toBeInTheDocument();
  });
});

describe("CounselorLeadsPanel", () => {
  it("lists the counselor's leads with links to the detail", async () => {
    render(<CounselorLeadsPanel division="overseas" />);
    const link = await screen.findByRole("link", { name: "LD-000042" });
    expect(link).toHaveAttribute("href", "/overseas/counselor/leads/L1");
    expect(screen.getByRole("cell", { name: "Counselling Completed" })).toBeInTheDocument();  // ccrm-012: the Stage filter lists it too
  });

  it("offers a retry when the list fails", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    render(<CounselorLeadsPanel division="it" />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "LD-000042" })).toBeInTheDocument();
  });

  // ccrm-004 (DEC-SCOPE-259 LG1-LG3): the counselor's calls, messages and meetings on their own lead
  it("logs a call on the counselor's route, without the telecaller's stage effect note", async () => {
    const call = { id: "K1", lead_id: "L1", occurred_at: "2026-10-25T05:00:00Z", duration_seconds: 120, call_type: "outgoing", outcome: "not_interested",
      outcome_label: "Not Interested", connected: true, remarks: null, caller: { id: "c1", full_name: "Cara Counselor" }, created_at: "2026-10-25T05:00:00Z", can_change: true };
    reply["POST /calls"] = () => res({ call, lead: { id: "L1", status: "counselling_completed", status_label: "Counselling Completed" }, follow_up_id: null }, 201);
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Log call" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "not_interested" } });
    expect(screen.queryByText(/closes the lead/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save call" }));
    await screen.findByText("Call logged.");
    expect(body("POST", "/calls")).toMatchObject({ outcome: "not_interested", call_type: "outgoing" });
  });

  it("records a meeting with its mode and notes", async () => {
    reply["POST /meetings"] = () => res({ id: "M1", occurred_at: "2026-10-25T05:00:00Z", mode: "Online", notes: "Shortlist", author: { id: "c1", full_name: "Cara Counselor" }, created_at: "2026-10-25T05:00:00Z" }, 201);
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record meeting" }));
    fireEvent.click(screen.getByRole("button", { name: "Save meeting" }));
    expect(await screen.findByText("Add what was discussed")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "Online" } });
    fireEvent.change(screen.getByLabelText("Notes (required)"), { target: { value: "  Shortlist  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save meeting" }));
    await screen.findByText("Meeting recorded.");
    expect(body("POST", "/meetings")).toMatchObject({ mode: "Online", notes: "Shortlist" });
  });

  it("reads the messages from the counselor's route and offers both channels", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    expect(await screen.findByRole("button", { name: "Send WhatsApp" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send email" })).toBeEnabled();
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/v1/counselor/leads/L1/messages"))).toBe(true));
  });

  it("offers no activity on a closed lead", async () => {
    render(<CounselorLeadDetail initial={detail({ status: "lost", status_label: "Lost", permissions: closedPermissions })} />);
    expect(await screen.findByRole("heading", { name: "Calls" })).toBeInTheDocument();
    for (const name of ["Log call", "Send WhatsApp", "Send email", "Record meeting"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  });
});
