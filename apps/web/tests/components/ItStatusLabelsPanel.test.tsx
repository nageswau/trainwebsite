import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ItStatusLabelsPanel from "@/components/ItStatusLabelsPanel";
import { ADMIN_STATUS_LABELS_URL } from "@/lib/statusLabels";

// itc-005 (DEC-SCOPE-362): the IT Admin's page -- rename (+ case), turn a chosen state off (with the in-use count), never offer turning
// off a system state, show the API's refusal, and the load failure with Retry.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (code: string, label: string, extra: Record<string, unknown> = {}) => ({
  code, label, default_label: label, sort_order: 10, enabled: true, can_disable: true, in_use: 0, updated_at: null, updated_by: null, ...extra,
});
const catalogue = (interested = "Interested") => ({
  lead: [row("contacted", "Contacted", { can_disable: false }), { ...row("interested", interested, { in_use: 3 }), default_label: "Interested" }],
  lifecycle: [row("closed", "Closed")],
});

let fetchMock: ReturnType<typeof vi.fn>;
let current = catalogue();
beforeEach(() => {
  current = catalogue();
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === ADMIN_STATUS_LABELS_URL) return Promise.resolve(res(current));
    if (init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      if (body.label === "Qualified") return Promise.resolve(res({ detail: [{ loc: ["body", "label"], msg: "Another status already uses this label" }] }, 422));
      current = catalogue(body.label);
      return Promise.resolve(res({}));
    }
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ItStatusLabelsPanel (itc-005)", () => {
  it("renames Interested to Course Interested", async () => {
    render(<ItStatusLabelsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Interested" }));
    fireEvent.change(screen.getByLabelText("Label (required)"), { target: { value: "Course Interested" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Interested label" }));
    expect(await screen.findByText("Saved Course Interested.")).toBeTruthy();
    expect(await screen.findByText("Course Interested")).toBeTruthy();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/admin/it/status-labels/lead/interested");
    expect(JSON.parse(put[1].body)).toEqual({ label: "Course Interested", sort_order: 10, enabled: true });
  });

  it("turns a chosen state off, saying how many records keep it, and never offers it for a system state", async () => {
    render(<ItStatusLabelsPanel />);
    expect(await screen.findByRole("button", { name: "Turn off Interested" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Turn off Contacted" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Turn off Interested" }));
    expect(await screen.findByText("Turned off Interested. 3 existing records keep it.")).toBeTruthy();
  });

  it("shows the API's refusal and keeps the form open", async () => {
    render(<ItStatusLabelsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Interested" }));
    fireEvent.change(screen.getByLabelText("Label (required)"), { target: { value: "Qualified" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Interested label" }));
    expect(await screen.findByText(/already uses this label/)).toBeTruthy();
    expect(screen.getByLabelText("Label (required)")).toBeTruthy();
  });

  it("checks the label before sending", async () => {
    render(<ItStatusLabelsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Interested" }));
    fireEvent.change(screen.getByLabelText("Label (required)"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save Interested label" }));
    expect(await screen.findByText("Enter a label.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("offers Retry when the list cannot load", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    render(<ItStatusLabelsPanel />);
    expect(await screen.findByText("Unable to load the status labels.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    const leads = await screen.findByRole("region", { name: "Lead stages" });
    await waitFor(() => expect(within(leads).getByText("Interested")).toBeTruthy());
  });
});
