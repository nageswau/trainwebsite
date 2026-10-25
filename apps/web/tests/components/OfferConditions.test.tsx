import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationOffersPanel from "@/components/ApplicationOffersPanel";
import { conditionProblem } from "@/lib/applicationOffers";

// ccrm-024 (DEC-SCOPE-260): an offer's conditions inside the counselor's Offers panel -- list, add, update with evidence (C2) or a
// note (C5), read-only on a superseded offer (C3), and the all-satisfied prompt (C4).
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const condition = (over: Record<string, unknown> = {}) => ({
  id: "c1", description: "IELTS 6.5 overall", owner: "student", owner_label: "Student", due_date: "2026-11-20", status: "open", status_label: "Open",
  evidence: null, note: null, status_changed_at: null, ...over,
});
const summary = (over: Record<string, unknown> = {}) => ({ total: 1, satisfied: 0, open: 1, failed: 0, all_satisfied: false, ...over });
const offer = (over: Record<string, unknown> = {}) => ({
  id: "o1", offer_type: "conditional", offer_type_label: "Conditional", issue_date: "2026-10-01", offer_deadline: null, conditions: "IELTS 6.5 overall",
  currency: null, tuition_amount: null, scholarship_amount: null, deposit_amount: null, deposit_deadline: null, document: null, status: "active",
  status_reason: null, recorded_by: "Asha", recorded_at: "2026-10-01T10:00:00Z", closed_by: null, closed_at: null, decision: "considering",
  decision_label: "Considering", decision_date: null, decided_by: null, condition_items: [condition()], conditions_summary: summary(), ...over,
});
const payload = (over: Record<string, unknown> = {}) => ({ offers: [offer()], offer_letters: [], evidence_documents: [{ id: "e1", name: "ielts.pdf" }], agency: false, ...over });
const CONDITIONS = "/api/v1/workflows/overseas/applications/a1/offers/o1/conditions";

function mount(data: unknown, write: (url: string, init: RequestInit) => Promise<unknown> = () => json({ changed: true }, true, 201)) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method ? write(url, init) : json(data)));
  vi.stubGlobal("fetch", fetchMock);
  const onChanged = vi.fn();
  render(<ApplicationOffersPanel applicationId="a1" onChanged={onChanged} />);
  return { fetchMock, onChanged };
}

describe("conditionProblem", () => {
  it("needs evidence for met and a note for waived or failed", () => {
    expect(conditionProblem("met", false, "")).toMatch(/evidence/);
    expect(conditionProblem("met", true, "")).toBeNull();
    expect(conditionProblem("waived", false, " ")).toMatch(/note/);
    expect(conditionProblem("failed", false, "Missed")).toBeNull();
    expect(conditionProblem("open", false, "")).toBeNull();
  });
});

describe("OfferConditions", () => {
  it("lists the conditions with owner, due date, status and progress", async () => {
    mount(payload());
    const list = await screen.findByRole("list", { name: "Conditions" });
    expect(within(list).getByText("IELTS 6.5 overall", { selector: "span:not(.visually-hidden)" })).toBeInTheDocument();
    expect(within(list).getByText("Open")).toBeInTheDocument();
    expect(within(list).getByText(/Owner: Student · Due 2026-11-20/)).toBeInTheDocument();
    expect(screen.getByText(/0 of 1 conditions satisfied/)).toBeInTheDocument();
  });

  it("adds a condition; the agent owner is offered only on an agency application", async () => {
    const { fetchMock, onChanged } = mount(payload());
    fireEvent.click(await screen.findByRole("button", { name: "Add condition" }));
    expect(screen.queryByRole("option", { name: "Agent" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Condition"), { target: { value: "Final transcript" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "counselor" } });
    fireEvent.change(screen.getByLabelText("Due date (optional)"), { target: { value: "2026-12-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Condition added."));
    const post = fetchMock.mock.calls.find(([url, init]) => url === CONDITIONS && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ description: "Final transcript", owner: "counselor", due_date: "2026-12-01" });
  });

  it("offers the agent owner on an agency application", async () => {
    mount(payload({ agency: true }));
    fireEvent.click(await screen.findByRole("button", { name: "Add condition" }));
    expect(screen.getByRole("option", { name: "Agent" })).toBeInTheDocument();
  });

  it("marks a condition met with picked evidence and refuses met without it", async () => {
    const { fetchMock, onChanged } = mount(payload(), () => json({ changed: true }));
    fireEvent.click(await screen.findByRole("button", { name: /Update condition/ }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "met" } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition" }));
    expect(await screen.findByText("Attach the evidence before marking the condition met.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    fireEvent.change(screen.getByLabelText("Evidence"), { target: { value: "e1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Condition updated."));
    const patch = fetchMock.mock.calls.find(([url, init]) => url === `${CONDITIONS}/c1` && init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ status: "met", evidence_document_id: "e1", note: null });
  });

  it("uploads new evidence before saving", async () => {
    const { fetchMock, onChanged } = mount(payload({ evidence_documents: [] }), (url) =>
      url.endsWith("/condition-evidence") ? json({ document: { id: "e9", name: "scan.pdf" } }, true, 201) : json({ changed: true }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /Update condition/ }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "met" } });
    fireEvent.change(screen.getByLabelText(/Upload evidence/), { target: { files: [new File(["%PDF"], "scan.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Condition updated."));
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body)).evidence_document_id).toBe("e9");
  });

  it("shows a server refusal on the form", async () => {
    mount(payload(), () => json({ detail: "Conditions can be changed only on the current offer" }, false, 409));
    fireEvent.click(await screen.findByRole("button", { name: /Update condition/ }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "waived" } });
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: "University waived it" } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition" }));
    expect(await screen.findByText("Conditions can be changed only on the current offer")).toBeInTheDocument();
  });

  it("is read-only on a superseded offer", async () => {
    mount(payload({ offers: [offer({ status: "superseded" })] }));
    expect(await screen.findByText("IELTS 6.5 overall")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add condition" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Update condition/ })).not.toBeInTheDocument();
  });

  it("prompts for an unconditional offer once every condition is satisfied (C4)", async () => {
    const met = condition({ status: "met", status_label: "Met", evidence: { id: "e1", name: "ielts.pdf" } });
    mount(payload({ offers: [offer({ condition_items: [met], conditions_summary: summary({ satisfied: 1, open: 0, all_satisfied: true }) })] }));
    expect(await screen.findByText(/All conditions satisfied/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record unconditional offer" }));
    expect(screen.getByRole("form", { name: "Record offer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Unconditional")).toBeChecked();
  });
});
