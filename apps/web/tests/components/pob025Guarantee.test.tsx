import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PlacementDetail from "@/components/PlacementDetail";
import { type Guarantee, type Placement, PLACEMENT_TABS } from "@/lib/placements";

// pob-025 (DEC-SCOPE-436 G3-G12): the placement's replacement guarantee panel -- status, end date and days left; recording a dropout;
// linking the owed replacement to an open requirement of the client; the replacement hire's "No fee (replacement)".
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/recruiter/placements/P1" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const guarantee = (over: Partial<Guarantee> = {}): Guarantee => ({
  days: 90, end_date: "2027-01-30", status: "active", status_label: "In guarantee", days_left: 83, dropout: null, replacement: null, replaces: null, ...over,
});
const placement = (over: Partial<Placement> = {}): Placement => ({
  id: "P1", status: "joined", status_label: "Joined", role: "Java Developer", offer_id: "O1", application: { id: "A1", code: "APP-1" },
  candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" },
  company: { id: "CO1", name: "Acme Technologies" }, vendor: null, recruiter: null, po_owner: null, source: null, package: null,
  joining: { expected_joining_date: "2026-11-01", actual_joining_date: "2026-11-01" }, candidate_confirmation: null, client_confirmation: null,
  commercials: null, guarantee: guarantee(),
  permissions: { can_edit: true, can_change_owner: false, can_invoice: false, can_record_dropout: true, can_request_replacement: false }, ...over,
});
const owed = guarantee({
  status: "dropped_out", status_label: "Dropped out", days_left: null, dropout: { on: "2026-11-05", reason: "Left for a higher offer" },
  replacement: { status: "open", status_label: "Replacement owed", requirement: null, placement: null },
});
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const panel = () => screen.getByRole("region", { name: "Replacement guarantee" });

describe("PlacementDetail guarantee (pob-025)", () => {
  it("shows the status, the end date and the days left (AC1)", () => {
    render(<PlacementDetail initial={placement()} />);
    const g = panel();
    expect(within(g).getByText("In guarantee")).toBeInTheDocument();
    expect(within(g).getByText("90 days")).toBeInTheDocument();
    expect(within(g).getByText("83")).toBeInTheDocument();
  });

  it("records a dropout and announces the owed replacement (AC2); a 422 lands on its field", async () => {
    fetchMock
      .mockResolvedValueOnce(res({ detail: [{ loc: ["body", "dropout_on"], msg: "The dropout date cannot be in the future" }] }, 422))
      .mockResolvedValueOnce(res({ placement: placement({ guarantee: owed, permissions: { ...placement().permissions, can_record_dropout: false, can_request_replacement: true } }) }));
    render(<PlacementDetail initial={placement()} />);
    fireEvent.click(within(panel()).getByRole("button", { name: "Record dropout" }));
    fireEvent.change(screen.getByLabelText("Why did the candidate leave?"), { target: { value: "Left for a higher offer" } });
    fireEvent.submit(screen.getByRole("form", { name: "Record dropout" }));
    expect(await screen.findByText("The dropout date cannot be in the future")).toBeInTheDocument();
    expect(screen.getByLabelText("Left on")).toHaveAttribute("aria-invalid", "true");
    fireEvent.submit(screen.getByRole("form", { name: "Record dropout" }));
    expect(await screen.findByText("Dropout recorded. A replacement is owed.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/recruiter/placements/P1/dropout");
    expect(JSON.parse(init.body as string)).toMatchObject({ reason: "Left for a higher offer" });
    expect(within(panel()).getByText("Replacement owed")).toBeInTheDocument();
    expect(within(panel()).getByText("Reason: Left for a higher offer")).toBeInTheDocument();
  });

  it("links an open requirement of the client for the replacement (G6)", async () => {
    const requested = { ...owed, replacement: { status: "requested" as const, status_label: "Replacement in progress", requirement: { id: "J2", code: "REQ-000002", title: "Java Developer II" }, placement: null } };
    fetchMock
      .mockResolvedValueOnce(res({ items: [{ id: "J2", code: "REQ-000002", title: "Java Developer II", status: "open" }, { id: "J3", code: "REQ-000003", title: "Old", status: "closed" }], total: 2 }))
      .mockResolvedValueOnce(res({ placement: placement({ guarantee: requested, permissions: { ...placement().permissions, can_record_dropout: false, can_request_replacement: true } }) }));
    render(<PlacementDetail initial={placement({ guarantee: owed, permissions: { ...placement().permissions, can_record_dropout: false, can_request_replacement: true } })} />);
    fireEvent.click(within(panel()).getByRole("button", { name: "Link replacement requirement" }));
    const select = await screen.findByLabelText("Replacement requirement");
    expect(within(select).queryByText("Old (REQ-000003)")).not.toBeInTheDocument(); // an ended requirement is not offered
    expect(String(fetchMock.mock.calls[0][0])).toContain("company_id=CO1");
    fireEvent.change(select, { target: { value: "J2" } });
    fireEvent.click(screen.getByRole("button", { name: "Link requirement" }));
    expect(await screen.findByText("Replacement requirement linked.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({ job_id: "J2" });
    expect(within(panel()).getByText("Replacement in progress")).toBeInTheDocument();
  });

  it("offers no action without the permissions, and marks a replacement hire's fee", () => {
    const replacement = placement({
      guarantee: guarantee({ replaces: { id: "P0", candidate: { id: "C0", code: "CAN-000000", name: "Anil Shah" } } }),
      commercials: { expected_fee: "0.00", invoice: { status: "none", status_label: "No draft yet", draft_amount: null, draft_due_date: null, draft_created_at: null, discard_reason: null, invoice: null } },
      permissions: { can_edit: false, can_change_owner: false, can_invoice: false, can_record_dropout: false, can_request_replacement: false },
    });
    render(<PlacementDetail initial={replacement} />);
    expect(within(panel()).queryByRole("button")).not.toBeInTheDocument();
    expect(within(panel()).getByRole("link", { name: "Anil Shah (CAN-000000)" })).toHaveAttribute("href", "/recruiter/placements/P0");
    expect(screen.getByText("No fee (replacement)")).toBeInTheDocument();
    expect(screen.getByText("A replacement hire gets no invoice draft.")).toBeInTheDocument();
    expect(screen.queryByText("No draft yet")).not.toBeInTheDocument(); // QA-02: no draft is coming
    expect(within(screen.getByRole("region", { name: "Invoice" })).getByText("Not invoiced")).toBeInTheDocument();
  });

  it("moves focus into each form when it opens, so Escape closes it (QA-01)", async () => {
    render(<PlacementDetail initial={placement()} />);
    fireEvent.click(within(panel()).getByRole("button", { name: "Record dropout" }));
    expect(screen.getByLabelText("Left on")).toHaveFocus();
    fireEvent.keyDown(screen.getByLabelText("Left on"), { key: "Escape" });
    expect(screen.queryByRole("form", { name: "Record dropout" })).not.toBeInTheDocument();
    cleanup();
    fetchMock.mockResolvedValueOnce(res({ items: [{ id: "J2", code: "REQ-000002", title: "Java Developer II", status: "open" }], total: 1 }));
    render(<PlacementDetail initial={placement({ guarantee: owed, permissions: { ...placement().permissions, can_record_dropout: false, can_request_replacement: true } })} />);
    fireEvent.click(within(panel()).getByRole("button", { name: "Link replacement requirement" }));
    expect(await screen.findByLabelText("Replacement requirement")).toHaveFocus();
  });

  it("lists a Replacements tab", () => {
    expect(PLACEMENT_TABS.map(([key]) => key)).toContain("replacements");
  });
});
