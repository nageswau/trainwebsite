import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminCertificatePanel from "@/components/AdminCertificatePanel";
import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";
import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

// nehn-002: ticking "Override unmet criteria" must collect a real reason and send it as `override_reason`
// (the API answers 422 without one); a blank/whitespace reason is stopped in the browser, and no-override is unchanged.
const ISSUE = "/api/v1/workflows/it/certificates/e1/issue";
const CONTEXT = { batches: [{ id: "b1", name: "Batch A", schedule: "Mon", capacity: 20 }], students: [], enrollments: [{ id: "e1", student_id: "s1", student: "Asha Rao", batch_id: "b1", batch: "Batch A", enrollment_code: "EDU-1", progress_percent: 70 }] };
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function stubFetch() {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (url === ISSUE && init?.method === "POST") return json({ id: "c1", certificate_no: "EDU-CERT-2026-AB12", status: "issued" }, 201);
    if (url === "/api/v1/workflows/it/trainer/context") return json(CONTEXT);
    if (url === "/api/v1/workflows/it/certificates/eligibility/e1") return json({ eligible: false, progress_percent: 70, attendance_percent: 70, assignments_graded: 0, assignments_total: 1, assessments_passed: 0, assessments_total: 1, pending_fee: 0 });
    if (url.startsWith("/api/v1/admin/enrollments")) return json([{ id: "e1", student: "Asha Rao", batch: "Batch A", progress_percent: 70 }]);
    return json([]);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
const issueBody = (mock: ReturnType<typeof stubFetch>) => {
  const call = mock.mock.calls.find(([url, init]) => url === ISSUE && init?.method === "POST");
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderTrainerCard() {
  const mock = stubFetch();
  render(<TeacherWorkspaceActions section="student-progress" />);
  const learner = await screen.findByLabelText("Eligible learner");
  await screen.findAllByRole("option", { name: /Asha Rao · Batch A · EDU-1/ });
  fireEvent.change(learner, { target: { value: "e1" } });
  return mock;
}
const issueButton = () => screen.getByRole("button", { name: "Issue certificate" });

describe("trainer Issue certificate card (nehn-002)", () => {
  it("AC1: with override ticked and a reason, sends the trimmed override_reason", async () => {
    const mock = await renderTrainerCard();
    expect(screen.queryByLabelText(/Override reason/)).toBeNull();
    fireEvent.click(screen.getByLabelText("Override unmet criteria"));
    fireEvent.change(screen.getByLabelText(/Override reason/), { target: { value: "  Prior industry certification accepted.  " } });
    fireEvent.click(issueButton());
    expect(await screen.findByText("Certificate issued.")).toBeInTheDocument();
    expect(issueBody(mock)).toEqual({ override: true, override_reason: "Prior industry certification accepted." });
  });

  it.each(["", "   "])("AC2: with override ticked and reason %j, shows a validation message and sends nothing", async (reason) => {
    const mock = await renderTrainerCard();
    fireEvent.click(screen.getByLabelText("Override unmet criteria"));
    fireEvent.change(screen.getByLabelText(/Override reason/), { target: { value: reason } });
    fireEvent.submit(issueButton().closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a reason for the override.");
    expect(issueBody(mock)).toBeUndefined();
  });

  it("AC3: without override, the request is unchanged", async () => {
    const mock = await renderTrainerCard();
    fireEvent.click(issueButton());
    expect(await screen.findByText("Certificate issued.")).toBeInTheDocument();
    expect(issueBody(mock)).toEqual({ override: false });
  });

  it("after a successful override, the checkbox and the reason field reset together", async () => {
    await renderTrainerCard();
    const override = screen.getByLabelText("Override unmet criteria");
    fireEvent.click(override);
    fireEvent.change(screen.getByLabelText(/Override reason/), { target: { value: "Accepted." } });
    fireEvent.click(issueButton());
    expect(await screen.findByText("Certificate issued.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText(/Override reason/)).toBeNull());
    expect(override).not.toBeChecked();
  });
});

describe("admin Issue certificate panel (nehn-002)", () => {
  it("a whitespace-only override reason is stopped in the browser", async () => {
    const mock = stubFetch();
    render(<AdminCertificatePanel />);
    const select = await screen.findByLabelText("Enrolment");
    await screen.findByRole("option", { name: /Asha Rao/ });
    fireEvent.change(select, { target: { value: "e1" } });
    fireEvent.change(await screen.findByLabelText(/Override reason/), { target: { value: "   " } });
    fireEvent.submit(screen.getByRole("button", { name: "Issue certificate" }).closest("form")!);
    expect(await screen.findByText("Enter a reason for the override.")).toBeInTheDocument();
    expect(issueBody(mock)).toBeUndefined();
  });
});

describe("WorkflowPanel trainer specs (nehn-002)", () => {
  it("no longer carry the reason-less Issue certificate form (trainers use TeacherWorkspaceActions)", () => {
    stubFetch();
    const trainer = { id: "t1", email: "t@example.local", full_name: "Tina Trainer", role: "trainer", division: "it" } as unknown as User;
    render(<WorkflowPanel user={trainer} section="student-progress" />);
    expect(screen.queryByRole("heading", { name: "Issue certificate" })).toBeNull();
    expect(screen.queryByLabelText("Override unmet criteria")).toBeNull();
  });
});
