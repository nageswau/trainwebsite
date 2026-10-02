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

// GET answers with `get`; PUT with a fresh `put()` Response (a body reads once), defaulting to `get` as well.
const api = (get: unknown, put: () => Response = () => json({ application: get })) =>
  vi.fn((_: string, init?: RequestInit) => Promise.resolve(init?.method === "PUT" ? put() : json({ application: get })));

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
    const fetchMock = api(detail(), () => json({ application: enrolled }));
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
    // QA13-01: the header badge is the final status; the section lists only what enrollment added (no repeated badge, course or intake).
    expect(screen.getAllByText("Enrolled", { selector: ".badge" })).toHaveLength(1);
    const section = screen.getByRole("region", { name: "Enrollment" });
    expect(within(section).queryByText("Course")).toBeNull();
    expect(within(section).queryByText("Sep 2027")).toBeNull();
    expect(within(section).getByText("2027-10-05")).toBeInTheDocument();
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
    mount(api(detail()));
    await openAndFill();
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm enrollment" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Confirm enrollment" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm enrollment" })).toHaveFocus());
  });

  it("a 422 keeps the form and the input, and announces the server's words", async () => {
    const fetchMock = api(detail(), () => json({ detail: "An offer is needed before enrollment" }, 422));
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
    mount(api(detail()), false);
    expect(await screen.findByText("An agency Master confirms enrollment.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enroll student" })).toBeNull();
  });

  it("an enrolled application shows the final status and details; a Master corrects them without a confirmation step", async () => {
    const fetchMock = api(enrolled, () => json({ application: { ...enrolled, university_student_id: "S-2" } }));
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
    mount(api(detail()));
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Enroll student" })).toHaveFocus());
  });

  it("Staff see enrolled details read-only", async () => {
    mount(api(enrolled), false);
    expect(await screen.findByText("S-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit enrollment details" })).toBeNull();
  });

  // Browser QA pass 2 (docs/quality/AGN-013_BROWSER_QA_2026-10-02_PASS2.md).
  async function confirmWith(put: () => Response) {
    mount(api(detail(), put));
    await openAndFill("2027-09-20");
    fireEvent.click(screen.getByRole("button", { name: "Yes, confirm enrollment" }));
  }

  it("QA13-03: an expired session says so, keeps the input and links to sign in again", async () => {
    await confirmWith(() => json({ detail: "Not authenticated" }, 401));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your session has expired. Your entry is kept; sign in again in a new tab, then save.");
    const link = within(alert).getByRole("link", { name: "Sign in again" });
    expect(link).toHaveAttribute("href", "/overseas/login");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByLabelText("Enrollment date (required)")).toHaveValue("2027-09-20");
  });

  it("QA13-08: a server error says it is on our side and that the entry is kept", async () => {
    await confirmWith(() => new Response("Internal Server Error", { status: 500 }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again; your entry is kept.");
    expect(screen.getByLabelText("Enrollment date (required)")).toHaveValue("2027-09-20");
  });

  it("QA13-09: a 422 on the student ID marks that field, describes it and focuses it", async () => {
    const detail422 = [{ type: "value_error", loc: ["body", "university_student_id"], msg: "Value error, must not contain control or bidirectional-override characters" }];
    await confirmWith(() => json({ detail: detail422 }, 422));
    const field = screen.getByLabelText("University student ID (optional)");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription("Must not contain control or bidirectional-override characters");
    await waitFor(() => expect(field).toHaveFocus());
  });

  it("QA13-04: opening the form moves focus to the date field", async () => {
    mount(api(detail()));
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    await waitFor(() => expect(screen.getByLabelText("Enrollment date (required)")).toHaveFocus());
  });

  it("QA13-05: Cancel discards what was typed", async () => {
    mount(api(enrolled));
    fireEvent.click(await screen.findByRole("button", { name: "Edit enrollment details" }));
    fireEvent.change(screen.getByLabelText("University student ID (optional)"), { target: { value: "TYPO" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit enrollment details" }));
    expect(screen.getByLabelText("University student ID (optional)")).toHaveValue("S-1");
  });

  it("QA13-06: other status actions are hidden while the enrollment form is open", async () => {
    mount(api(detail()));
    expect(await screen.findByRole("button", { name: "Withdraw application" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enroll student" }));
    expect(screen.queryByRole("button", { name: "Withdraw application" })).toBeNull();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Withdraw application" })).toBeInTheDocument();
  });

  it("QA13-07: editing replaces the read-only details instead of repeating them", async () => {
    mount(api(enrolled));
    fireEvent.click(await screen.findByRole("button", { name: "Edit enrollment details" }));
    const section = screen.getByRole("region", { name: "Enrollment" });
    expect(within(section).queryByText("Confirmed by the agency")).toBeNull();
    expect(within(section).queryByText("S-1")).toBeNull(); // only in the input now
  });

  it("before an offer, withdrawn or archived there is no enrollment section", async () => {
    for (const over of [{ status: "enquiry" }, { status: "withdrawn", read_only_reason: "withdrawn" }, { read_only_reason: "archived" }]) {
      mount(api(detail(over)));
      await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
      expect(screen.queryByRole("heading", { name: "Enrollment" })).toBeNull();
      cleanup();
    }
  });
});
