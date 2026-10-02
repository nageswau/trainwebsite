import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: "MSc Data", course_id: "c1", intake: "Sep 2027", status: "offer", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], enrollment_date: null, university_student_id: null, enrollment_confirmed_at: null, enrollment_check: null, ...over,
});
const enrolled = detail({ status: "enrolled", enrollment_date: "2027-10-05", university_student_id: "S-1", enrollment_confirmed_at: "2026-10-02T10:00:00Z", enrollment_check: "after_intake" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(fetchMock: ReturnType<typeof vi.fn>, isMaster = true) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AgentApplicationDetail id="a1" isMaster={isMaster} onChanged={vi.fn()} onClose={vi.fn()} />);
}

async function openAndFill(value = "2027-10-05") {
  fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
  fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
}

describe("AgentApplicationEnrollment (AGN-013)", () => {
  it("a Master confirms after an explicit confirmation step, sending the displayed status", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "PUT" ? enrolled : detail() })));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    const form = screen.getByRole("form", { name: "Enrollment" });
    expect(within(form).getByText("Uni One")).toBeInTheDocument();
    expect(within(form).getByText("Sep 2027")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value: "2027-10-05" } });
    fireEvent.change(screen.getByLabelText("University student ID (optional)"), { target: { value: " S-1 " } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
    const confirm = screen.getByRole("group", { name: "Confirm enrollment" });
    expect(within(confirm).getByText(/commission will be estimated/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PUT")).toBe(false); // nothing is sent before "Yes"
    fireEvent.click(within(confirm).getByRole("button", { name: "Yes, confirm enrollment" }));
    await waitFor(() => expect(screen.getByText("Enrollment confirmed.")).toHaveFocus());
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/workflows/overseas/agent/crm/applications/a1/enrollment");
    expect(JSON.parse(String(put[1]!.body))).toEqual({ enrollment_date: "2027-10-05", university_student_id: "S-1", expected_status: "offer", notes: null });
    const section = screen.getByRole("region", { name: "Enrollment" });
    expect(within(section).getByText("Enrolled", { selector: ".badge" })).toBeInTheDocument();
    expect(within(section).getByText(/after the intake month/)).toHaveClass("form-warning");
  });

  it("sends one request on a double click and shows it is saving", async () => {
    let resolvePut: (r: Response) => void = () => {};
    const fetchMock = vi.fn((_: string, init?: RequestInit) => (init?.method === "PUT" ? new Promise<Response>((r) => (resolvePut = r)) : Promise.resolve(json({ application: detail() }))));
    mount(fetchMock);
    await openAndFill();
    const yes = screen.getByRole("button", { name: "Yes, confirm enrollment" });
    fireEvent.click(yes);
    fireEvent.click(yes);
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "PUT")).toHaveLength(1);
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    resolvePut(json({ application: enrolled }));
    await screen.findByText("Enrollment confirmed.");
  });

  it("Escape on the confirmation goes back and returns focus to the submit button", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: detail() }))));
    await openAndFill();
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm enrollment" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Confirm enrollment" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm enrollment" })).toHaveFocus());
  });

  it("a 422 keeps the form and the input, and announces the server's words", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(init?.method === "PUT" ? json({ detail: "An offer is needed before enrollment" }, 422) : json({ application: detail() })));
    mount(fetchMock);
    await openAndFill("2027-09-20");
    fireEvent.click(screen.getByRole("button", { name: "Yes, confirm enrollment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An offer is needed before enrollment");
    expect(screen.getByLabelText("Enrollment date (required)")).toHaveValue("2027-09-20");
  });

  it("a 409 shows the server's words and reloads to the real state", async () => {
    let put = false;
    const fetchMock = vi.fn((_: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        put = true;
        return Promise.resolve(json({ detail: "This application changed since you opened it -- reload to see its current status" }, 409));
      }
      return Promise.resolve(json({ application: put ? detail({ status: "enrolled" }) : detail() }));
    });
    mount(fetchMock);
    await openAndFill();
    fireEvent.click(screen.getByRole("button", { name: "Yes, confirm enrollment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(await screen.findByRole("button", { name: "Add enrollment details" })).toBeInTheDocument();
  });

  it("Staff see who confirms, not the action", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: detail() }))), false);
    expect(await screen.findByText("An agency Master confirms enrollment.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enroll student" })).toBeNull();
  });

  it("an enrolled application shows the final status and details; a Master corrects them without a confirmation step", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "PUT" ? { ...enrolled, university_student_id: "S-2" } : enrolled })));
    mount(fetchMock);
    expect(await screen.findByText("S-1")).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit enrollment details" }));
    expect(screen.getByLabelText("Enrollment date (required)")).toHaveValue("2027-10-05");
    fireEvent.change(screen.getByLabelText("University student ID (optional)"), { target: { value: "S-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save enrollment details" }));
    await screen.findByText("Enrollment details saved.");
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ enrollment_date: "2027-10-05", university_student_id: "S-2", expected_status: "enrolled" });
  });

  it("Cancel closes the form and returns focus to its opener", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: detail() }))));
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Enroll student" })).toHaveFocus());
  });

  it("Staff see enrolled details read-only", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: enrolled }))), false);
    expect(await screen.findByText("S-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit enrollment details" })).toBeNull();
  });

  it("before an offer, withdrawn or archived there is no enrollment section", async () => {
    for (const over of [{ status: "enquiry" }, { status: "withdrawn", read_only_reason: "withdrawn" }, { read_only_reason: "archived" }]) {
      mount(vi.fn(() => Promise.resolve(json({ application: detail(over) }))));
      await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
      expect(screen.queryByRole("heading", { name: "Enrollment" })).toBeNull();
      cleanup();
    }
  });
});
