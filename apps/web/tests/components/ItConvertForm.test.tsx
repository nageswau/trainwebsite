import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadDetail from "@/components/CounselorLeadDetail";
import ItConvertForm from "@/components/ItConvertForm";
import ItOnboardingChecklist from "@/components/ItOnboardingChecklist";
import { convertBody, entryProblem } from "@/lib/itConversion";
import type { CounselorLeadDetail as Detail } from "@/lib/leadHandover";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/it/counselor/leads", useSearchParams: () => new URLSearchParams() }));

// itc-011: the one-step IT conversion form, the onboarding checklist and their place on the counselor's lead.
const URL_ = "/api/v1/counselor/leads/L1/convert-it";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const batch = (id: string, over = {}) => ({ id, name: `PY-${id}`, program_id: `P-${id}`, program: "Python Full Stack", fee: 50000, start_date: "2026-12-15",
  end_date: "2027-03-15", schedule: "Mon-Fri", mode: "online", available: 5, recommended: false, ...over });
const options = (over = {}) => ({
  prefill: { full_name: "Asha Rao", email: "asha@example.com", phone: "9876543210", fee: 45000, recommended_program_id: "P-B1", recommended_course: "Python Full Stack" },
  batches: [batch("B1", { recommended: true }), batch("B2", { program: "Data Science", fee: 60000 })],
  checklist: ["Set your password and sign in", "Accept the enrolment agreement"],
  ...over,
});
const items = [{ id: "I1", label: "Set your password and sign in", position: 1, done: false, done_at: null }, { id: "I2", label: "Accept the enrolment agreement", position: 2, done: false, done_at: null }];
const result = (over = {}) => ({
  student: { id: "S9", full_name: "Asha Rao", email: "asha@example.com", student_code: "ST1", setup: "pending_setup" },
  enrollment: { id: "E1", enrollment_code: "EDU-20261103-ABC123", status: "pending_consent", course: "Python Full Stack", batch: "PY-B1" },
  fee_account: {}, checklist: items, replayed: false, email_status: "sent",
  lead: { id: "L1", status: "application_enrollment", converted_user: { id: "S9", full_name: "Asha Rao", email: "asha@example.com" } },
  ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
let reply: Record<string, () => Response>;
beforeEach(() => {
  reply = { [`GET ${URL_}`]: () => res(options()), [`POST ${URL_}`]: () => res(result(), 201) };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    return Promise.resolve(reply[key] ? reply[key]() : res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const posts = () => fetchMock.mock.calls.filter(([u, i]) => u === URL_ && i?.method === "POST");
const sent = (n = 0) => JSON.parse(String(posts()[n][1].body));
const keyOf = (n = 0) => (posts()[n][1].headers as Record<string, string>)["Idempotency-Key"];

async function openForm(props: Partial<Parameters<typeof ItConvertForm>[0]> = {}) {
  const onConverted = vi.fn();
  render(<ItConvertForm url={URL_} onConverted={onConverted} {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Convert to IT student" }));
  await screen.findByLabelText("Batch");
  return onConverted;
}

describe("ItConvertForm", () => {
  it("prefills from the lead and counseling, previews the checklist and converts with an Idempotency-Key", async () => {
    const onConverted = await openForm();
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha Rao");
    expect(screen.getByLabelText("Email")).toHaveValue("asha@example.com");
    expect(screen.getByLabelText("Fee (INR)")).toHaveValue(45000);
    expect(screen.getByLabelText("Batch")).toHaveValue("B1");
    expect(screen.getByText("Accept the enrolment agreement")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "B2" } });
    expect(screen.getByLabelText("Fee (INR)")).toHaveValue(45000); // the quoted fee is kept when the batch changes
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    await waitFor(() => expect(onConverted).toHaveBeenCalled());
    expect(sent()).toEqual({ student: { full_name: "Asha Rao", email: "asha@example.com", phone: "9876543210" }, batch_id: "B2", fee: "45000.00", installments: [] });
    expect(keyOf()).toMatch(/^[A-Za-z0-9._:-]{1,120}$/);
  });

  it("uses the course fee when no fee was quoted, and follows the batch until the fee is edited", async () => {
    reply[`GET ${URL_}`] = () => res(options({ prefill: { ...options().prefill, fee: null } }));
    await openForm();
    expect(screen.getByLabelText("Fee (INR)")).toHaveValue(50000);
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "B2" } });
    expect(screen.getByLabelText("Fee (INR)")).toHaveValue(60000);
  });

  it("sends installments and refuses a plan that does not add up, without calling the API", async () => {
    await openForm();
    fireEvent.click(screen.getByRole("button", { name: "Add installment" }));
    fireEvent.change(screen.getByLabelText("Installment 1 amount"), { target: { value: "20000" } });
    fireEvent.change(screen.getByLabelText("Installment 1 due date"), { target: { value: "2026-12-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    expect(await screen.findByText("The installments must add up to the fee.")).toBeInTheDocument();
    expect(posts()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Add installment" }));
    fireEvent.change(screen.getByLabelText("Installment 2 amount"), { target: { value: "25000" } });
    fireEvent.change(screen.getByLabelText("Installment 2 due date"), { target: { value: "2027-01-01" } });
    expect(screen.getByText(/Planned ₹45,000.00 of ₹45,000.00/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(sent().installments).toEqual([{ amount: "20000.00", due_date: "2026-12-01" }, { amount: "25000.00", due_date: "2027-01-01" }]);
  });

  it("keeps the entry and the key on a refusal, so a resubmit is the same conversion", async () => {
    reply[`POST ${URL_}`] = () => res({ detail: "This batch is full" }, 409);
    const onConverted = await openForm();
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    expect(await screen.findByText("This batch is full")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(keyOf(1)).toBe(keyOf(0));
    expect(onConverted).not.toHaveBeenCalled();
  });

  it("offers the existing IT student on a duplicate and enrols them by id", async () => {
    reply[`POST ${URL_}`] = () => res({ detail: { code: "student_exists", message: "An IT student already has this email or mobile. Link the existing student instead." } }, 409);
    reply["GET /api/v1/counselor/leads/L1/link-suggestions"] = () => res({ items: [{ id: "S1", full_name: "Asha R", email: "asha@example.com", phone: null, linked_elsewhere: false },
      { id: "S2", full_name: "Taken", email: "t@example.com", phone: null, linked_elsewhere: true }] });
    await openForm({ suggestionsUrl: "/api/v1/counselor/leads/L1/link-suggestions" });
    fireEvent.click(screen.getByRole("button", { name: "Convert and enrol" }));
    expect(await screen.findByText(/An IT student already has this email/)).toBeInTheDocument();
    const group = await screen.findByRole("group", { name: "Existing IT students" });
    expect(within(group).queryByText(/Taken/)).not.toBeInTheDocument();
    reply[`POST ${URL_}`] = () => res(result({ student: { id: "S1", full_name: "Asha R", email: "asha@example.com", student_code: "ST0", setup: null }, email_status: undefined }), 201);
    fireEvent.click(within(group).getByRole("button", { name: "Enrol Asha R" }));
    expect(screen.queryByLabelText("Full name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enrol existing student" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(sent(1)).toEqual({ student_id: "S1", batch_id: "B1", fee: "45000.00", installments: [] });
  });

  it("says so when no batch has a seat, and cannot be submitted", async () => {
    reply[`GET ${URL_}`] = () => res(options({ batches: [] }));
    render(<ItConvertForm url={URL_} onConverted={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to IT student" }));
    expect(await screen.findByText("No open batch has a seat left. Ask the IT Admin to open one.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Convert and enrol" })).toBeDisabled();
  });

  it("offers a retry when the batches cannot be loaded", async () => {
    reply[`GET ${URL_}`] = () => res({}, 500);
    render(<ItConvertForm url={URL_} onConverted={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to IT student" }));
    expect(await screen.findByText(/Couldn.t load the batches/)).toBeInTheDocument();
    reply[`GET ${URL_}`] = () => res(options());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Batch")).toBeInTheDocument();
  });
});

describe("itConversion helpers", () => {
  const entry = { full_name: "A", email: "a@example.com", phone: "", batch_id: "B1", fee: "100", installments: [] };
  it("checks the entry before sending", () => {
    expect(entryProblem(entry, false)).toBeNull();
    expect(entryProblem({ ...entry, email: " " }, false)).toBe("Add the student's name and email.");
    expect(entryProblem({ ...entry, email: "" }, true)).toBeNull(); // an existing student needs no account details
    expect(entryProblem({ ...entry, batch_id: "" }, false)).toBe("Choose a batch.");
    expect(entryProblem({ ...entry, fee: "-1" }, false)).toBe("Enter a fee of 0 or more.");
    expect(entryProblem({ ...entry, fee: "0", installments: [{ amount: "1", due_date: "2027-01-01" }] }, false)).toBe("A fee of 0 takes no installments.");
    expect(entryProblem({ ...entry, installments: [{ amount: "33.33", due_date: "2027-01-01" }, { amount: "66.67", due_date: "2027-02-01" }] }, false)).toBeNull();
  });
  it("sends a blank phone as null", () => {
    expect(convertBody(entry, null)).toEqual({ student: { full_name: "A", email: "a@example.com", phone: null }, batch_id: "B1", fee: "100.00", installments: [] });
  });
});

describe("ItOnboardingChecklist", () => {
  it("loads the items and ticks one", async () => {
    reply["GET /api/v1/it/enrollments/E1/onboarding"] = () => res({ enrollment_id: "E1", items });
    reply["PATCH /api/v1/it/enrollments/E1/onboarding/I1"] = () => res({ enrollment_id: "E1", items: [{ ...items[0], done: true }, items[1]] });
    render(<ItOnboardingChecklist enrollmentId="E1" canTick />);
    const box = await screen.findByRole("checkbox", { name: "Set your password and sign in" });
    expect(screen.getByText("0 of 2 done")).toBeInTheDocument();
    fireEvent.click(box);
    await waitFor(() => expect(box).toBeChecked());
    expect(screen.getByText("1 of 2 done")).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")![1].body))).toEqual({ done: true });
  });
  it("shows the tick at once, before the API answers (QA11-01)", async () => {
    let answer: (r: Response) => void = () => undefined;
    reply["PATCH /api/v1/it/enrollments/E1/onboarding/I1"] = () => new Promise<Response>((resolve) => { answer = resolve; }) as unknown as Response;
    render(<ItOnboardingChecklist enrollmentId="E1" canTick initial={items} />);
    const box = screen.getByRole("checkbox", { name: "Set your password and sign in" });
    fireEvent.click(box);
    expect(box).toBeChecked();
    answer(res({ enrollment_id: "E1", items: [{ ...items[0], done: true }, items[1]] }));
    await waitFor(() => expect(screen.getByText("1 of 2 done")).toBeInTheDocument());
    expect(box).toBeChecked();
  });

  it("keeps the old state and says why when a tick is refused", async () => {
    reply["PATCH /api/v1/it/enrollments/E1/onboarding/I1"] = () => res({ detail: "Enrolment not found" }, 404);
    render(<ItOnboardingChecklist enrollmentId="E1" canTick initial={items} />);
    const box = screen.getByRole("checkbox", { name: "Set your password and sign in" });
    fireEvent.click(box);
    expect(await screen.findByText("Enrolment not found")).toBeInTheDocument();
    expect(box).not.toBeChecked();
  });
});

describe("CounselorLeadDetail IT conversion", () => {
  const lead = (over: Partial<Detail> = {}): Detail => ({
    id: "L1", lead_code: "LD-000042", name: "Asha Rao", email: "asha@example.com", phone: "9876543210", whatsapp_number: null, city: null, state: null,
    qualification: null, passing_year: null, institution: null, division: "it", subject: "Python", status: "qualified", status_label: "Qualified",
    source: "website", priority: "warm", created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z", product: null, campaign: null,
    telecaller: null, counselor: { id: "c1", full_name: "Cara Counselor" }, converted_user: null, message: "", milestones: { student: null, items: [] },
    next_action: null, next_action_due: null, next_action_overdue: false, whatsapp_to: null, contact_preference: null, enquiry_date: "2026-10-06",
    marketing_opt_in: null, marketing_consent_at: null, referral_name: null, referral_contact: null, it_conversion: null,
    permissions: { return: true, link: true, unlink: false, stage: true, follow_up: true, convert: false, activity: true, convert_it: true }, ...over,
  });

  beforeEach(() => {
    const pages = ["/timeline", "/notes", "/follow-ups", "/calls", "/messages", "/meetings", "/counseling"];
    const inner = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const tail = url.replace("/api/v1/counselor/leads/L1", "");
      if (pages.some((t) => tail.startsWith(t))) return Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }));
      return inner(url, init);
    });
  });

  it("converts and then shows the outcome, the student link and the checklist", async () => {
    reply[`POST ${URL_}`] = () => res(result({ lead: lead({ status: "application_enrollment", status_label: "Application/Enrollment",
      converted_user: { id: "S9", full_name: "Asha Rao", email: "asha@example.com" }, it_conversion: { enrollment_id: "E1" },
      permissions: { return: false, link: false, unlink: true, stage: true, follow_up: true, convert: false, activity: true, convert_it: false } }) }), 201);
    render(<CounselorLeadDetail initial={lead()} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to IT student" }));
    fireEvent.click(await screen.findByRole("button", { name: "Convert and enrol" }));
    expect(await screen.findByText(/Student account created and enrolled in PY-B1 \(EDU-20261103-ABC123\)\. A set-password link was emailed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the student's profile" })).toHaveAttribute("href", "/it/counselor/students/S9/profile");
    expect(screen.getByRole("heading", { name: "Onboarding checklist" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Accept the enrolment agreement" })).toBeInTheDocument();
  });

  it("explains why an IT lead before Qualified cannot be converted yet", () => {
    render(<CounselorLeadDetail initial={lead({ status: "contacted", status_label: "Contacted", permissions: { ...lead().permissions, convert_it: false } })} />);
    expect(screen.queryByRole("button", { name: "Convert to IT student" })).not.toBeInTheDocument();
    expect(screen.getByText("Move the lead to Qualified to convert it to a new student.")).toBeInTheDocument();
  });
});
