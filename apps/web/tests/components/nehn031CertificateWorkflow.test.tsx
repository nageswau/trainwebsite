import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminCertificatePanel from "@/components/AdminCertificatePanel";
import CoordinatorCertificateQueue from "@/components/CoordinatorCertificateQueue";
import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

// nehn-031 (DEC-ROLE-003, DEC-SCOPE-294): the trainer recommends, the coordinator issues from a queue (singly or in bulk, with a
// reason when overriding), the admin sets the thresholds.
const BASE = "/api/v1/workflows/it/certificates";
const RULES = { min_progress_percent: 100, min_attendance_percent: 75 };
const CRITERIA = { progress_percent: 70, attendance_percent: 80, assignments_graded: 1, assignments_total: 2, assessments_passed: 0, assessments_total: 1, pending_fee: 0, rules: RULES };
const CONTEXT = { batches: [{ id: "b1", name: "Batch A", schedule: "Mon", capacity: 20 }], students: [], enrollments: [{ id: "e1", student_id: "s1", student: "Asha Rao", batch_id: "b1", batch: "Batch A", enrollment_code: "EDU-1", progress_percent: 70 }] };
const item = (id: string, student: string, eligible: boolean, recommendation: unknown = null) => ({
  enrollment_id: id, student, batch: "Batch A", program: "Java Full Stack", eligible, criteria: { ...CRITERIA, eligible }, recommendation,
});
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

type Routes = Record<string, (init?: RequestInit) => Promise<Response>>;
function stubFetch(routes: Routes) {
  const mock = vi.fn((url: string, init?: RequestInit) => (routes[`${init?.method ?? "GET"} ${url}`] ?? (() => json([])))(init));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const bodyOf = (mock: ReturnType<typeof stubFetch>, method: string, url: string) => {
  const call = mock.mock.calls.find(([u, init]) => u === url && init?.method === method);
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("trainer Recommend for certificate card", () => {
  async function renderCard() {
    const mock = stubFetch({
      "GET /api/v1/workflows/it/trainer/context": () => json(CONTEXT),
      [`GET ${BASE}/eligibility/e1`]: () => json({ ...CRITERIA, eligible: false }),
      [`POST ${BASE}/e1/recommend`]: () => json({ enrollment_id: "e1", status: "recommended", comment: null }),
    });
    render(<TeacherWorkspaceActions section="student-progress" />);
    await screen.findAllByRole("option", { name: /Asha Rao · Batch A · EDU-1/ });
    fireEvent.change(screen.getByLabelText("Learner"), { target: { value: "e1" } });
    return mock;
  }
  const send = () => screen.getByRole("button", { name: "Send recommendation" });

  it("no longer offers to issue a certificate", async () => {
    await renderCard();
    expect(screen.queryByRole("button", { name: "Issue certificate" })).toBeNull();
    expect(screen.queryByLabelText("Override unmet criteria")).toBeNull();
  });

  it("shows the learner's eligibility once picked", async () => {
    await renderCard();
    expect(await screen.findByText(/Not yet eligible: progress 70% \(needs 100%\)/)).toBeInTheDocument();
  });

  it("recommends with a trimmed comment", async () => {
    const mock = await renderCard();
    fireEvent.change(screen.getByLabelText(/Comment/), { target: { value: "  Strong final project.  " } });
    fireEvent.click(send());
    expect(await screen.findByText("Recommended to the coordinator.")).toBeInTheDocument();
    expect(bodyOf(mock, "POST", `${BASE}/e1/recommend`)).toEqual({ status: "recommended", comment: "Strong final project." });
  });

  it("says when the learner already holds a certificate and does not offer to send (QA31-04)", async () => {
    stubFetch({
      "GET /api/v1/workflows/it/trainer/context": () => json(CONTEXT),
      [`GET ${BASE}/eligibility/e1`]: () => json({ ...CRITERIA, eligible: true, certificate_issued: true }),
    });
    render(<TeacherWorkspaceActions section="student-progress" />);
    await screen.findAllByRole("option", { name: /Asha Rao · Batch A · EDU-1/ });
    fireEvent.change(screen.getByLabelText("Learner"), { target: { value: "e1" } });
    expect(await screen.findByText("A certificate has already been issued for this learner.")).toBeInTheDocument();
    expect(send()).toBeDisabled();
  });

  it("a not-ready flag needs a comment; none is sent without one", async () => {
    const mock = await renderCard();
    fireEvent.click(screen.getByLabelText("Not ready yet"));
    fireEvent.submit(send().closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Say why the learner is not ready.");
    expect(bodyOf(mock, "POST", `${BASE}/e1/recommend`)).toBeUndefined();
  });
});

describe("coordinator certificate queue", () => {
  const recommended = { status: "recommended", comment: "Strong final project.", by: "Tara Trainer", at: "2026-10-27T10:00:00Z" };
  const queue = (overrides = {}) => ({ can_override: true, rules: RULES, items: [item("e1", "Asha Rao", true), item("e2", "Ravi Kumar", false, recommended)], ...overrides });

  it("shows loading, then each learner's eligibility and the trainer's recommendation", async () => {
    stubFetch({ [`GET ${BASE}/queue`]: () => json(queue()) });
    render(<CoordinatorCertificateQueue />);
    expect(screen.getByText("Loading the certificate queue…")).toBeInTheDocument();
    const ravi = (await screen.findByText("Ravi Kumar")).closest("tr")!;
    expect(within(ravi).getByText("Not eligible")).toBeInTheDocument();
    expect(within(ravi).getByText(/Recommended by Tara Trainer/)).toBeInTheDocument();
    expect(within(ravi).getByText(/Strong final project\./)).toBeInTheDocument();
    expect(within(screen.getByText("Asha Rao").closest("tr")!).getByText("Eligible")).toBeInTheDocument();
  });

  it("keeps the issue button above the table, so a long queue needs no scrolling to act (QA31-01)", async () => {
    stubFetch({ [`GET ${BASE}/queue`]: () => json(queue()) });
    render(<CoordinatorCertificateQueue />);
    const table = await screen.findByRole("table");
    const button = screen.getByRole("button", { name: "Issue selected (0)" });
    expect(button.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the empty and error states", async () => {
    stubFetch({ [`GET ${BASE}/queue`]: () => json(queue({ items: [] })) });
    render(<CoordinatorCertificateQueue />);
    expect(await screen.findByText("No learners are waiting for a certificate.")).toBeInTheDocument();
    cleanup();
    stubFetch({ [`GET ${BASE}/queue`]: () => json({ detail: "You do not have permission to issue certificates" }, 403) });
    render(<CoordinatorCertificateQueue />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to issue certificates");
  });

  it("bulk-issues the selected eligible learners without an override", async () => {
    const mock = stubFetch({
      [`GET ${BASE}/queue`]: () => json(queue()),
      [`POST ${BASE}/issue`]: () => json({ issued: [{ enrollment_id: "e1", certificate_no: "EDU-CERT-1" }], failed: [] }),
    });
    render(<CoordinatorCertificateQueue />);
    fireEvent.click(await screen.findByLabelText("Select Asha Rao"));
    fireEvent.click(screen.getByRole("button", { name: "Issue selected (1)" }));
    expect(await screen.findByText("Issued 1 certificate.")).toBeInTheDocument();
    expect(bodyOf(mock, "POST", `${BASE}/issue`)).toEqual({ enrollment_ids: ["e1"], override: false });
  });

  it("stays busy until the queue has reloaded, so an issued learner cannot be sent twice (QA31-05)", async () => {
    let finishReload: (value: Response) => void = () => {};
    let loads = 0;
    stubFetch({
      [`GET ${BASE}/queue`]: () => (++loads === 1 ? json(queue()) : new Promise<Response>((resolve) => { finishReload = resolve; })),
      [`POST ${BASE}/issue`]: () => json({ issued: [{ enrollment_id: "e1" }], failed: [] }),
    });
    render(<CoordinatorCertificateQueue />);
    fireEvent.click(await screen.findByLabelText("Select Asha Rao"));
    fireEvent.click(screen.getByRole("button", { name: "Issue selected (1)" }));
    expect(await screen.findByText("Issued 1 certificate.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Issuing…" })).toBeDisabled();
    finishReload(new Response(JSON.stringify(queue({ items: [item("e2", "Ravi Kumar", false)] }))));
    expect(await screen.findByRole("button", { name: "Issue selected (0)" })).toBeDisabled();
    expect(screen.queryByText("Asha Rao")).toBeNull();
  });

  it("asks for a reason when a selected learner is not eligible, then sends the override", async () => {
    const mock = stubFetch({
      [`GET ${BASE}/queue`]: () => json(queue()),
      [`POST ${BASE}/issue`]: () => json({ issued: [{ enrollment_id: "e1" }], failed: [{ enrollment_id: "e2", status_code: 409, detail: "A certificate has already been issued for this enrolment" }] }),
    });
    render(<CoordinatorCertificateQueue />);
    fireEvent.click(await screen.findByLabelText("Select all"));
    expect(screen.getByRole("button", { name: "Issue selected (2)" })).toBeInTheDocument();
    fireEvent.submit(screen.getByRole("button", { name: "Issue selected (2)" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a reason for the override.");
    expect(bodyOf(mock, "POST", `${BASE}/issue`)).toBeUndefined();

    fireEvent.change(screen.getByLabelText(/Override reason/), { target: { value: "  Trainer recommended.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Issue selected (2)" }));
    expect(await screen.findByText(/Issued 1 certificate\. 1 not issued: Ravi Kumar — A certificate has already been issued/)).toBeInTheDocument();
    expect(bodyOf(mock, "POST", `${BASE}/issue`)).toEqual({ enrollment_ids: ["e1", "e2"], override: true, override_reason: "Trainer recommended." });
  });

  it("without the override permission, learners who are not eligible cannot be selected", async () => {
    stubFetch({ [`GET ${BASE}/queue`]: () => json(queue({ can_override: false })) });
    render(<CoordinatorCertificateQueue />);
    expect(await screen.findByLabelText("Select Ravi Kumar")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Select all"));
    expect(screen.getByRole("button", { name: "Issue selected (1)" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Override reason/)).toBeNull();
  });
});

describe("admin certificate rules panel", () => {
  it("loads the thresholds and saves a change", async () => {
    const mock = stubFetch({
      [`GET ${BASE}/rules`]: () => json(RULES),
      [`PUT ${BASE}/rules`]: (init) => json(JSON.parse(String(init?.body))),
    });
    render(<AdminCertificatePanel />);
    const progress = await screen.findByLabelText("Minimum progress (%)");
    await waitFor(() => expect(progress).toHaveValue(100));
    fireEvent.change(progress, { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Certificate rules saved. They apply to the next eligibility check.")).toBeInTheDocument();
    expect(bodyOf(mock, "PUT", `${BASE}/rules`)).toEqual({ min_progress_percent: 90, min_attendance_percent: 75 });
    expect(screen.queryByRole("button", { name: "Issue certificate" })).toBeNull();
  });

  it("shows the API's refusal", async () => {
    stubFetch({
      [`GET ${BASE}/rules`]: () => json(RULES),
      [`PUT ${BASE}/rules`]: () => json({ detail: "You do not have permission to change certificate rules" }, 403),
    });
    render(<AdminCertificatePanel />);
    await waitFor(() => expect(screen.getByLabelText("Minimum progress (%)")).toHaveValue(100));
    fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to change certificate rules");
  });
});
