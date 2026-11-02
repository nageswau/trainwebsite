import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadMergeForm from "@/components/LeadMergeForm";

// itc-007 (DEC-SCOPE-339): Merge a duplicate -- compare by Lead ID, pick the values to keep, merge; the API's refusals are shown.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const URL = "/api/v1/telecaller/leads/S1";
const side = (over: Record<string, unknown>) => ({
  id: "x", lead_code: "LD-1", status: "contacted", status_label: "Contacted", name: "Asha", email: "a@x.in", phone: null, whatsapp_number: null,
  city: null, state: null, qualification: null, passing_year: null, institution: null, ...over,
});
const preview = {
  survivor: side({ id: "S1", lead_code: "LD-000001" }),
  victim: side({ id: "V1", lead_code: "LD-000002", name: "Asha Rao", city: "Pune" }),
  moved: { calls: 2, follow_ups: 1, notes: 0, messages: 0, meetings: 0, appointments: 0, enquiries: 1, tasks: 0 },
};

let fetchMock: ReturnType<typeof vi.fn>;
let previewStatus: number;
beforeEach(() => {
  previewStatus = 200;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res({ id: "S1", victim_id: "V1", victim_code: "LD-000002", moved: preview.moved }));
    if (previewStatus !== 200) return Promise.resolve(res({ detail: "Lead not found" }, previewStatus));
    return Promise.resolve(res(preview));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function compare(code = "ld-000002") {
  fireEvent.click(screen.getByRole("button", { name: "Merge a duplicate into LD-000001" }));
  fireEvent.change(screen.getByLabelText("Lead ID of the duplicate"), { target: { value: code } });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
}

describe("LeadMergeForm", () => {
  it("asks for a Lead ID before comparing", () => {
    render(<LeadMergeForm url={URL} leadCode="LD-000001" onMerged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Merge a duplicate into LD-000001" }));
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(screen.getByText("Enter the Lead ID of the duplicate lead.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("compares both leads side by side with what will move", async () => {
    render(<LeadMergeForm url={URL} leadCode="LD-000001" onMerged={vi.fn()} />);
    await compare();
    expect(fetchMock).toHaveBeenCalledWith(`${URL}/merge-preview?victim=LD-000002`, expect.anything());
    const table = await screen.findByRole("table", { name: "Compare the two leads" });
    const nameRow = within(table).getByRole("row", { name: /Student name/ });
    expect(within(nameRow).getByText("Asha")).toBeTruthy();
    expect(within(nameRow).getByText("Asha Rao")).toBeTruthy();
    // an empty field here is filled from the duplicate: no choice offered
    const cityRow = within(table).getByRole("row", { name: /City/ });
    expect(within(cityRow).queryByRole("radio")).toBeNull();
    // browser QA-02: "Label: count", never "1 enquiries"
    expect(screen.getByText("Moves to this lead: Calls: 2, Follow-ups: 1, Enquiries: 1.")).toBeTruthy();
    // browser QA-01: on a phone each cell stacks under its column's label
    expect(table.className).toContain("stack");
    expect(within(nameRow).getAllByRole("cell").map((td) => td.getAttribute("data-label"))).toEqual(["This lead (LD-000001)", "Duplicate (LD-000002)"]);
  });

  it("sends the fields picked from the duplicate and reports the merge", async () => {
    const onMerged = vi.fn();
    render(<LeadMergeForm url={URL} leadCode="LD-000001" onMerged={onMerged} />);
    await compare();
    await screen.findByRole("table", { name: "Compare the two leads" });
    fireEvent.click(screen.getByRole("radio", { name: "Keep Asha Rao for Student name" }));
    fireEvent.change(screen.getByLabelText("Reason (optional)"), { target: { value: " Same phone " } });
    fireEvent.click(screen.getByRole("button", { name: "Merge into this lead" }));
    await waitFor(() => expect(onMerged).toHaveBeenCalledWith("LD-000002"));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe(`${URL}/merge`);
    expect(JSON.parse(String(post[1].body))).toEqual({ victim: "LD-000002", use_victim: ["name"], reason: "Same phone" });
  });

  it("shows the API's refusal of the comparison", async () => {
    previewStatus = 404;
    render(<LeadMergeForm url={URL} leadCode="LD-000001" onMerged={vi.fn()} />);
    await compare();
    expect(await screen.findByText("Lead not found")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("Cancel closes the form and returns focus to its button", async () => {
    render(<LeadMergeForm url={URL} leadCode="LD-000001" onMerged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Merge a duplicate into LD-000001" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Merge a duplicate into LD-000001" })));
  });
});
