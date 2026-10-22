import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorEvaluationPanel from "@/components/CounselorEvaluationPanel";
import { subStatusChoices, subStatusLabel } from "@/lib/applicationSubStatus";

// ccrm-014 (DEC-SCOPE-240): the sub-status choices and the counselor's card form.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const row = (over: Record<string, unknown> = {}) => ({ id: "a1", student: "Ravi", university: "U1", reference: null, status: "offer", sub_status: "conditional_offer", sub_status_label: "Conditional offer", next_action: null, is_agency: false, ...over });

describe("subStatusChoices", () => {
  it("offers the current stage and later ones, without the value already set", () => {
    const groups = subStatusChoices("offer", "conditional_offer");
    expect(groups.map((g) => g.stage)).toEqual(["offer", "visa_documentation", "status_tracking", "enrolled"]);
    expect(groups[0].options).toEqual(["unconditional_offer", "offer_accepted"]);
  });

  it("stops at the cap and treats an early stage as the start", () => {
    expect(subStatusChoices("enquiry", null, "status_tracking").map((g) => g.stage)).toEqual(["university_selection", "offer", "visa_documentation", "status_tracking"]);
    expect(subStatusChoices("enrolled", "enrolled")).toEqual([]);
    expect(subStatusLabel("ready_for_submission")).toBe("Ready for submission");
  });
});

describe("counselor sub-status form", () => {
  it("shows the badge and posts the chosen sub-status", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return json({ id: "a1", status: "offer", sub_status: "offer_accepted", sub_status_label: "Offer accepted", changed: true });
      return json({ rows: [row()] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorEvaluationPanel />);
    const card = (await screen.findByRole("heading", { name: "Ravi" })).closest(".card") as HTMLElement;
    expect(within(card).getByText("Conditional offer")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Update sub-status" }));
    fireEvent.change(within(card).getByLabelText("Sub-status"), { target: { value: "offer_accepted" } });
    fireEvent.click(within(card).getByRole("button", { name: "Update sub-status" }));
    await waitFor(() => expect(within(card).getByText(/Sub-status updated to Offer accepted/)).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/workflows/overseas/applications/a1/sub-status");
    expect(JSON.parse(String(post[1]!.body))).toEqual({ sub_status: "offer_accepted", notes: null });
  });

  it("never offers Enrolled on an agency application and shows a server refusal", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => (init?.method === "POST" ? json({ detail: "This application is withdrawn" }, false, 409) : json({ rows: [row({ is_agency: true, status: "status_tracking", sub_status: null, sub_status_label: null })] }))));
    render(<CounselorEvaluationPanel />);
    const card = (await screen.findByRole("heading", { name: "Ravi" })).closest(".card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Update sub-status" }));
    const values = Array.from((within(card).getByLabelText("Sub-status") as HTMLSelectElement).options).map((o) => o.value);
    expect(values).toEqual(["visa_decision_pending", "visa_approved"]);
    fireEvent.click(within(card).getByRole("button", { name: "Update sub-status" }));
    expect(await within(card).findByText("This application is withdrawn")).toBeInTheDocument();
  });

  it("QA-03: Cancel closes the form without sending anything", async () => {
    const fetchMock = vi.fn(() => json({ rows: [row()] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorEvaluationPanel />);
    const card = (await screen.findByRole("heading", { name: "Ravi" })).closest(".card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Update sub-status" }));
    fireEvent.click(within(card).getByRole("button", { name: "Cancel" }));
    expect(within(card).queryByLabelText("Sub-status")).toBeNull();
    expect(within(card).getByRole("button", { name: "Update sub-status" })).toBeInTheDocument();
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    expect(calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });

  it("offers no sub-status form on a withdrawn application", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ rows: [row({ status: "withdrawn", sub_status: null, sub_status_label: null })] })));
    render(<CounselorEvaluationPanel />);
    const card = (await screen.findByRole("heading", { name: "Ravi" })).closest(".card") as HTMLElement;
    expect(within(card).queryByRole("button", { name: "Update sub-status" })).toBeNull();
  });
});
