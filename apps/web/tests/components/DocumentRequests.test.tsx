import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationChecklistPanel from "@/components/ApplicationChecklistPanel";
import CounselorDocumentRequestsPanel from "@/components/CounselorDocumentRequestsPanel";
import StudentDocumentRequestsPanel from "@/components/StudentDocumentRequestsPanel";

// ccrm-020 (DEC-SCOPE-265): the counselor's requests on the student 360, the student's "Requested documents", and the checklist row's
// "Request from student".
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const STAFF = "/api/v1/counselor/students/s1/document-requests";
const MINE = "/api/v1/overseas/me/document-requests";
const req = (over: Record<string, unknown> = {}) => ({
  id: "r1", document_type: "Other", document_label: "IELTS scorecard", name: "IELTS scorecard", note: "Academic, 6.5", status: "open", due_date: "2026-11-01",
  overdue: false, application_id: null, application_code: null, university: null, checklist_item_id: null, requested_by: "Counsellor A",
  created_at: "2026-10-25T05:00:00Z", closed_at: null, document: null, ...over,
});
const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });
type Fetch = (url: string, init?: RequestInit) => ReturnType<typeof json>;

describe("CounselorDocumentRequestsPanel", () => {
  it("lists requests with due date, overdue and the uploaded document, and creates one", async () => {
    let created = false;
    const fetchMock = vi.fn<Fetch>((url, init) => {
      if (init?.method === "POST") {
        created = true;
        return json({ request: req({ id: "r9" }) }, true, 201);
      }
      return json(page(created ? [req({ id: "r9" })] : [req({ overdue: true }), req({ id: "r2", name: "Passport", status: "fulfilled", document: { id: "d1", original_filename: "p.pdf", verification_status: "pending", status_label: "Pending review" } })]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorDocumentRequestsPanel studentId="s1" applications={[{ id: "a1", label: "APP-000001 · Oxford" }]} />);
    const first = (await screen.findByText("IELTS scorecard")).closest("li") as HTMLElement;
    expect(within(first).getByText("Overdue")).toBeInTheDocument();
    expect(within(first).getByText(/Academic, 6.5/)).toBeInTheDocument();
    const second = within(screen.getByRole("list")).getByText("Passport").closest("li") as HTMLElement;
    expect(within(second).getByText(/Pending review/)).toBeInTheDocument();
    expect(within(second).queryByRole("button", { name: /Cancel/ })).toBeNull(); // only open requests cancel

    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Other" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "IELTS scorecard" } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("Application (optional)"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Note to the student (optional)"), { target: { value: "Academic, 6.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === STAFF && init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ document_type: "Other", document_label: "IELTS scorecard", due_date: "2026-11-01", application_id: "a1", note: "Academic, 6.5" });
    expect(await screen.findByText("Request sent to the student.")).toBeInTheDocument();
  });

  it("shows why a request is open again and says when only part of the list is shown", async () => {
    vi.stubGlobal("fetch", vi.fn<Fetch>(() => json({ items: [req({ review_note: "Page 2 is missing" })], total: 25, limit: 20, offset: 0 })));
    render(<CounselorDocumentRequestsPanel studentId="s1" applications={[]} />);
    expect(await screen.findByText(/Reopened after review: Page 2 is missing/)).toBeInTheDocument();
    expect(screen.getByText("Showing the latest 1 of 25 requests.")).toBeInTheDocument();
  });

  it("cancels an open request and shows a server refusal", async () => {
    const fetchMock = vi.fn<Fetch>((url, init) => (init?.method === "POST" ? json({ detail: "This request has already been fulfilled or cancelled" }, false, 409) : json(page([req()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorDocumentRequestsPanel studentId="s1" applications={[]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel request for IELTS scorecard" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === `${STAFF}/r1/cancel` && init?.method === "POST")).toBe(true));
    expect(await screen.findByRole("alert")).toHaveTextContent("already been fulfilled or cancelled");
  });

  it("says when there are none and when the list fails", async () => {
    let fail = true;
    vi.stubGlobal("fetch", vi.fn<Fetch>(() => (fail ? json({ detail: "boom" }, false, 500) : json(page([])))));
    render(<CounselorDocumentRequestsPanel studentId="s1" applications={[]} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No document requests yet.")).toBeInTheDocument();
  });
});

describe("StudentDocumentRequestsPanel", () => {
  it("shows the open requests and uploads a file against one", async () => {
    let uploaded = false;
    const fetchMock = vi.fn<Fetch>((url, init) => {
      if (init?.method === "POST") {
        uploaded = true;
        return json({ request: req({ status: "fulfilled" }), document_id: "d1" }, true, 201);
      }
      return json(page(uploaded ? [] : [req({ overdue: true, review_note: "Page 2 is missing" })]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentDocumentRequestsPanel />);
    const row = (await screen.findByText("IELTS scorecard")).closest("li") as HTMLElement;
    expect(within(row).getByText("Overdue")).toBeInTheDocument();
    expect(within(row).getByText(/Please upload a new file: Page 2 is missing/)).toBeInTheDocument();
    expect(within(row).getByText(/Academic, 6.5/)).toBeInTheDocument();
    const file = new File(["%PDF-1.4"], "ielts.pdf", { type: "application/pdf" });
    fireEvent.change(within(row).getByLabelText("File for IELTS scorecard"), { target: { files: [file] } });
    fireEvent.click(within(row).getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === `${MINE}/r1/upload` && init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect((post[1]!.body as FormData).get("file")).toBeInstanceOf(File);
    expect(await screen.findByText(/IELTS scorecard uploaded/)).toBeInTheDocument();
    expect(await screen.findByText("No documents are requested from you right now.")).toBeInTheDocument();
  });
});

describe("ApplicationChecklistPanel request from student", () => {
  const item = (over: Record<string, unknown> = {}) => ({
    id: "i2", position: 1, document_type: "English test", label: "IELTS scorecard", name: "IELTS scorecard", required: true, notes: null, allowed_statuses: [],
    mark: null, status: "missing", status_label: "Missing", removable: true, documents: [], open_request: null, ...over,
  });
  const payload = (items: unknown[]) => ({
    checklist: { template_id: null, template_version: null, gate_mode: "warn", documents_completed_on: null, summary: { required_total: 1, required_complete: 0, optional_total: 0, optional_complete: 0, ready: false, missing: [] }, items },
    template: null, documents: [], student_id: "s1",
  });

  it("requests a missing item from the student and then shows its due date", async () => {
    let requested = false;
    const fetchMock = vi.fn<Fetch>((url, init) => {
      if (url === STAFF && init?.method === "POST") {
        requested = true;
        return json({ request: req() }, true, 201);
      }
      return json(payload([requested ? item({ mark: "requested", status: "requested", status_label: "Requested", open_request: { id: "r1", due_date: "2026-11-01" } }) : item()]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationChecklistPanel applicationId="a1" onChanged={vi.fn()} />);
    const row = (await screen.findByText("IELTS scorecard")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Request from student" }));
    fireEvent.change(within(row).getByLabelText("Due date for IELTS scorecard"), { target: { value: "2026-11-01" } });
    fireEvent.click(within(row).getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === STAFF && init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find(([url, init]) => url === STAFF && init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ due_date: "2026-11-01", application_id: "a1", checklist_item_id: "i2" });
    const after = (await screen.findByText(/Requested from the student · due/)).closest("li") as HTMLElement;
    expect(within(after).queryByRole("button", { name: "Request from student" })).toBeNull();
  });
});
