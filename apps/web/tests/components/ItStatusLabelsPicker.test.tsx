import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LeadStageControl } from "@/components/AdminLeadStage";
import { clearStatusLabels, STATUS_LABELS_URL } from "@/lib/statusLabels";

// itc-005 (DEC-SCOPE-362 AC1/AC2): an IT lead's stage picker shows the IT team's words and leaves out the stages the IT Admin turned
// off; an overseas lead's picker never asks for the IT catalogue and keeps the defaults.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const entry = (code: string, label: string, enabled = true) => ({ code, label, default_label: label, sort_order: 0, enabled, can_disable: true });
const catalogue = { lead: [entry("qualified", "Qualified"), entry("interested", "Course Interested"), entry("lost", "Lost", false)], lifecycle: [] };

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  clearStatusLabels();
  fetchMock = vi.fn((url: string) => Promise.resolve(url === STATUS_LABELS_URL ? res(catalogue) : res({ items: [], total: 0, limit: 100, offset: 0 })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const options = () => Array.from((screen.getByLabelText("New stage for Asha Rao") as HTMLSelectElement).options).map((o) => o.textContent);

function open(division: string) {
  render(<LeadStageControl lead={{ id: "L1", name: "Asha Rao", status: "contacted", division }} move={vi.fn()} onChanged={() => {}} onMessage={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
}

describe("LeadStageControl with the IT catalogue (itc-005)", () => {
  it("relabels and drops turned-off stages for an IT lead", async () => {
    open("it");
    await waitFor(() => expect(options()).toContain("Course Interested"));
    expect(options()).not.toContain("Interested");
    expect(options()).not.toContain("Lost");
    expect(options()).toContain("Not Interested");
  });

  it("keeps the defaults for an overseas lead without reading the IT catalogue", () => {
    open("overseas");
    expect(options()).toContain("Interested");
    expect(options()).toContain("Lost");
    expect(fetchMock).not.toHaveBeenCalledWith(STATUS_LABELS_URL, expect.anything());
  });
});
