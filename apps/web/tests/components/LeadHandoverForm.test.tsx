import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadHandoverForm from "@/components/LeadHandoverForm";
import LeadMilestones from "@/components/LeadMilestones";
import type { TelecallerLeadDetail } from "@/lib/telecallerLeads";

// tel-018 (spec §4; HO4): "Assign to counselor" on the lead detail, and the read-only milestones (T4).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const lead = (over: Partial<TelecallerLeadDetail> = {}) => ({
  id: "L1", lead_code: "LD-000042", name: "Asha Rao", status: "qualified", counselor: null, ...over,
}) as TelecallerLeadDetail;
const options = { types: [], modes: [], counselors: [{ id: "c1", full_name: "Cara Counselor" }, { id: "c2", full_name: "Dev Counselor" }] };

let fetchMock: ReturnType<typeof vi.fn>;
let post: () => Response;
beforeEach(() => {
  post = () => res({ ...lead(), counselor: { id: "c1", full_name: "Cara Counselor" }, read_only: true });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(post());
    if (url === "/api/v1/telecaller/leads/L1/appointment-options") return Promise.resolve(res(options));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadHandoverForm", () => {
  it("loads the division's counselors only when opened, then hands the lead over", async () => {
    const onDone = vi.fn();
    render(<LeadHandoverForm lead={lead()} onDone={onDone} />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Assign to counselor" }));
    const select = await screen.findByLabelText("Counselor");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a counselor", "Cara Counselor", "Dev Counselor"]);
    fireEvent.change(select, { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Hand over" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(url).toBe("/api/v1/telecaller/leads/L1/handover");
    expect(JSON.parse(String(init.body))).toEqual({ counselor_id: "c1" });
    expect(onDone.mock.calls[0][0].counselor.full_name).toBe("Cara Counselor");
  });

  it("requires a choice and shows the API's refusal", async () => {
    post = () => res({ detail: "This lead is closed; reopen it before handing it over" }, 409);
    render(<LeadHandoverForm lead={lead()} onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign to counselor" }));
    await screen.findByLabelText("Counselor");
    fireEvent.click(screen.getByRole("button", { name: "Hand over" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a counselor.");
    fireEvent.change(screen.getByLabelText("Counselor"), { target: { value: "c2" } });
    fireEvent.click(screen.getByRole("button", { name: "Hand over" }));
    expect(await screen.findByText("This lead is closed; reopen it before handing it over")).toBeInTheDocument();
  });

  it("a manager changes the counselor; the current one is not offered", async () => {
    render(<LeadHandoverForm lead={lead({ counselor: { id: "c1", full_name: "Cara Counselor" } })} onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change counselor" }));
    await screen.findByLabelText("Counselor");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a counselor", "Dev Counselor"]);
  });

  it("says so when the counselors can't be read, and Cancel closes", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    render(<LeadHandoverForm lead={lead()} onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign to counselor" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the counselors.");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Assign to counselor" })).toBeInTheDocument();
  });
});

describe("LeadMilestones", () => {
  it("says when no student is linked", () => {
    render(<LeadMilestones milestones={{ student: null, items: [] }} status="counselling_completed" />);
    expect(screen.getByText("No student account is linked yet.")).toBeInTheDocument();
    expect(screen.queryByText("Converted")).toBeNull();
  });

  it("lists the linked student's milestones and the Converted badge", () => {
    render(<LeadMilestones status="converted" milestones={{
      student: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" },
      items: [{ kind: "application", label: "Oxford", status: "offer_received", reference: "APP-1", at: "2026-10-01T00:00:00Z" },
        { kind: "visa", label: "Oxford", status: "checklist", reference: null, at: "2026-10-02T00:00:00Z" }],
    }} />);
    expect(screen.getByText("Converted")).toBeInTheDocument();
    expect(screen.getByText(/Asha Rao/)).toHaveTextContent("Asha Rao (asha@example.com)");
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(rows[0]).toContain("Overseas application");
    expect(rows[0]).toContain("Offer received");
    expect(rows[1]).toContain("Visa case");
  });
});
