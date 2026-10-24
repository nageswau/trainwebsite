import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationChecklistPanel from "@/components/ApplicationChecklistPanel";
import ApplicationSubStatusForm from "@/components/ApplicationSubStatusForm";

// ccrm-019 (DEC-SCOPE-257): the application checklist panel and the Ready-for-Submission gate in the sub-status form.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const BASE = "/api/v1/workflows/overseas/applications/a1/checklist";
const doc = (over: Record<string, unknown> = {}) => ({ id: "d1", document_type: "Passport", document_label: null, original_filename: "passport.pdf", verification_status: "verified", status_label: "Verified", created_at: "2026-10-01T00:00:00Z", ...over });
const item = (over: Record<string, unknown> = {}) => ({
  id: "i1", position: 1, document_type: "Passport", label: null, name: "Passport", required: true, notes: null, allowed_statuses: ["pending", "requested", "verified", "not_required"],
  mark: null, status: "verified", status_label: "Verified", removable: false, documents: [doc()], ...over,
});
const checklist = (items = [item(), item({ id: "i2", document_type: "Transcripts", name: "Transcripts", status: "missing", status_label: "Missing", documents: [] })]) => ({
  template_id: "t1", template_version: 3, gate_mode: "block", documents_completed_on: null,
  summary: { required_total: 2, required_complete: 1, optional_total: 0, optional_complete: 0, ready: false, missing: [{ id: "i2", label: "Transcripts", status: "missing", status_label: "Missing" }] },
  items,
});

describe("ApplicationChecklistPanel", () => {
  it("offers to create the checklist from the matching template and shows the summary", async () => {
    let created = false;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        created = true;
        return json({ checklist: checklist(), template: null, documents: [] }, true, 201);
      }
      return json({ checklist: created ? checklist() : null, template: { id: "t1", name: "UK admission", version: 3, gate_mode: "block" }, documents: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<ApplicationChecklistPanel applicationId="a1" onChanged={onChanged} />);
    expect(await screen.findByText(/No checklist yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Create checklist from UK admission \(v3\)/ }));
    expect(await screen.findByText("1 of 2 required complete")).toBeInTheDocument();
    expect(screen.getByText(/Block until complete/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => url === BASE && init?.method === "POST")).toBe(true);
    expect(onChanged).toHaveBeenCalledWith("Checklist created.");
  });

  it("marks an item requested, links a document and adds an item", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => ReturnType<typeof json>>(() => json({ checklist: checklist(), template: null, documents: [doc({ id: "d9", document_type: "Transcript", original_filename: "tr.pdf", verification_status: "pending", status_label: "Pending review" })] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationChecklistPanel applicationId="a1" onChanged={vi.fn()} />);
    const row = (await screen.findByText("Transcripts")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Mark requested" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === `${BASE}/items/i2` && init?.method === "PATCH")).toBe(true));
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ mark: "requested" });
    fireEvent.change(within(row).getByLabelText("Link a document to Transcripts"), { target: { value: "d9" } });
    fireEvent.click(within(row).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === `${BASE}/items/i2/documents/d9` && init?.method === "PUT")).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Other" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Portfolio" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to checklist" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === `${BASE}/items` && init?.method === "POST")).toBe(true));
    const add = fetchMock.mock.calls.find(([url, init]) => url === `${BASE}/items` && init?.method === "POST")!;
    expect(JSON.parse(String(add[1]!.body))).toEqual({ document_type: "Other", label: "Portfolio", required: true });
  });

  it("is read-only for the agency and shows a load error with a retry", async () => {
    let fail = true;
    vi.stubGlobal("fetch", vi.fn(() => (fail ? json({ detail: "Application is outside your assigned scope" }, false, 403) : json({ checklist: checklist(), template: null, documents: [] }))));
    render(<ApplicationChecklistPanel applicationId="a1" readOnly />);
    expect(await screen.findByText("Application is outside your assigned scope")).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("1 of 2 required complete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark requested" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add item" })).toBeNull();
  });
});

describe("Ready-for-Submission gate in the sub-status form", () => {
  const props = { id: "a1", url: "/api/v1/workflows/overseas/applications/a1/sub-status", stage: "university_selection", current: "documents_pending" };

  it("block mode lists the missing items and does not offer an override", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: { message: "Ready for Submission needs every required checklist document complete", gate_mode: "block", missing: [{ id: "i2", label: "Transcripts", status: "missing", status_label: "Missing" }] } }, false, 409)));
    const onFailed = vi.fn();
    render(<ApplicationSubStatusForm {...props} onSaved={vi.fn()} onFailed={onFailed} />);
    fireEvent.change(screen.getByLabelText("Sub-status"), { target: { value: "ready_for_submission" } });
    fireEvent.click(screen.getByRole("button", { name: "Update sub-status" }));
    expect(await screen.findByText(/needs every required checklist document complete/)).toBeInTheDocument();
    expect(screen.getByText("Transcripts — Missing")).toBeInTheDocument(); // browser QA-01
    expect(screen.queryByLabelText("Override reason")).toBeNull();
    expect(onFailed).not.toHaveBeenCalled();
  });

  it("warn mode asks for an override reason and resends with it", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init!.body));
      if (!body.override_reason) return json({ detail: { message: "Some required checklist documents are not complete -- give an override reason to continue", gate_mode: "warn", missing: [{ id: "i2", label: "Transcripts", status: "requested", status_label: "Requested" }] } }, false, 409);
      return json({ id: "a1", status: "university_selection", sub_status: "ready_for_submission", changed: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<ApplicationSubStatusForm {...props} onSaved={onSaved} onFailed={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Sub-status"), { target: { value: "ready_for_submission" } });
    fireEvent.click(screen.getByRole("button", { name: "Update sub-status" }));
    const reason = await screen.findByLabelText("Override reason");
    fireEvent.change(reason, { target: { value: "University accepts it later" } });
    fireEvent.click(screen.getByRole("button", { name: "Override and update" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]!.body))).toEqual({ sub_status: "ready_for_submission", notes: null, override_reason: "University accepts it later" });
  });
});
