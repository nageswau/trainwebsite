import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LeadStageControl } from "@/components/AdminLeadStage";
import LeadClosure from "@/components/LeadClosure";

// ccrm-006 (DEC-SCOPE-263, D3-D5): the stage control asks for the surviving Lead ID on Duplicate and a reason from the list (plus an
// optional "lost to") on Lost / Not Interested; the text reason is optional for those.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const reasons = { items: [{ id: "r1", name: "Fees / budget", active: true, sort_order: 1 }, { id: "r2", name: "Other", active: true, sort_order: 2 }], total: 2, limit: 100, offset: 0 };
const lead = { id: "L1", name: "Asha Rao", status: "contacted" };

let fetchMock: ReturnType<typeof vi.fn>;
let move: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn((url: string) => Promise.resolve(url.startsWith("/api/v1/telecaller/lost-reasons") ? res(reasons) : res({}, 404)));
  vi.stubGlobal("fetch", fetchMock);
  move = vi.fn(() => Promise.resolve({ ok: true, data: {} }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function open(target: string) {
  render(<LeadStageControl lead={lead} move={move} onChanged={() => {}} onMessage={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
  fireEvent.change(screen.getByLabelText("New stage for Asha Rao"), { target: { value: target } });
}

describe("LeadStageControl closure (ccrm-006)", () => {
  it("offers Duplicate and shows Wrong Number as Invalid Contact", () => {
    open("");
    const options = Array.from((screen.getByLabelText("New stage for Asha Rao") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(options).toContain("Duplicate");
    expect(options).toContain("Invalid Contact");
    expect(options).not.toContain("Wrong Number");
  });

  it("needs the surviving Lead ID for Duplicate and sends it", async () => {
    open("duplicate");
    expect(screen.getByLabelText("Reason (optional)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter the Lead ID of the lead this one duplicates.")).toBeTruthy();
    expect(move).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Duplicate of Lead ID (required)"), { target: { value: " ld-000042 " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith("L1", "duplicate", "", { duplicate_of: "LD-000042" }));
  });

  it("needs a reason from the list for Lost and sends it with Lost to", async () => {
    open("lost");
    const picker = await screen.findByLabelText("Lost reason (required)");
    await waitFor(() => expect((picker as HTMLSelectElement).options.length).toBe(3));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Choose why the lead was lost.")).toBeTruthy();
    fireEvent.change(picker, { target: { value: "r1" } });
    fireEvent.change(screen.getByLabelText("Lost to (optional)"), { target: { value: " Canada " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith("L1", "lost", "", { lost_reason_id: "r1", lost_to: "Canada" }));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/telecaller/lost-reasons?active=true&limit=100");
  });

  it("shows an error with Retry when the reason list fails", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    open("not_interested");
    expect(await screen.findByText("Unable to load the lost reasons.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Lost reason (required)")).toBeTruthy();
  });

  it("says when no lost reason is set up yet (QA-03)", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 })));
    open("lost");
    expect(await screen.findByText("No lost reasons are set up yet. Ask a telecaller manager to add one.")).toBeTruthy();
    expect(screen.queryByLabelText("Lost reason (required)")).toBeNull();
  });

  it("still requires the text reason for other closed outcomes", async () => {
    open("wrong_number");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Add a reason for this stage.")).toBeTruthy();
    expect(screen.queryByLabelText("Lost reason (required)")).toBeNull();
  });
});

describe("LeadClosure (ccrm-006)", () => {
  it("names the surviving lead or the loss reason, and nothing otherwise", () => {
    const { container, rerender } = render(<LeadClosure lead={{ duplicate_of: null, lost_reason: null, lost_to: null }} />);
    expect(container.textContent).toBe("");
    rerender(<LeadClosure lead={{ duplicate_of: { id: "L2", lead_code: "LD-000042" }, lost_reason: null, lost_to: null }} />);
    expect(screen.getByText("Duplicate of LD-000042")).toBeTruthy();
    rerender(<LeadClosure lead={{ duplicate_of: null, lost_reason: { id: "r1", name: "Fees / budget" }, lost_to: "Canada" }} />);
    expect(screen.getByText("Lost reason: Fees / budget · Lost to: Canada")).toBeTruthy();
  });
});
