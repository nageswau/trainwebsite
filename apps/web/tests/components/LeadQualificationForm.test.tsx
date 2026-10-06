import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadQualificationForm from "@/components/LeadQualificationForm";
import type { LeadQualification } from "@/lib/telecallerLeads";

// tel-009 (spec §4-§5, QF1-QF3, QD1-QD2): the qualification section of the lead detail -- basic fields always, the IT or overseas
// section by the product group, the other group's values kept but hidden, client range checks, the read-only view.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const EMPTY = {
  qualification: null, passing_year: null, city: null, state: null, current_org: null, work_experience_years: null, it_skill_level: null,
  career_objective: null, preferred_batch: null, budget_range: null, preferred_mode: null, study_level: null, preferred_course: null,
  intake: null, academic_percentage: null, english_test_status: null, passport_status: null,
};
const qual = (over: Partial<LeadQualification> = {}): LeadQualification => ({
  lead_id: "L1", product: { id: "p-uk", name: "UK", group: "overseas" }, product_group: "overseas", ...EMPTY, city: "Chennai",
  read_only: false, updated_by: null, updated_at: null, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
let getReply: () => Response;
let putReply: (body: Record<string, unknown>) => Response;
const puts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
beforeEach(() => {
  getReply = () => res(qual());
  putReply = (body) => res({ ...qual(), ...body, updated_by: { id: "t1", full_name: "Tara Caller" }, updated_at: "2026-10-06T07:00:00Z" });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (!url.startsWith("/api/v1/telecaller/leads/L1/qualification")) return Promise.resolve(res({}, 404));
    if (init?.method === "PUT") return Promise.resolve(putReply(JSON.parse(String(init.body))));
    return Promise.resolve(getReply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const edit = async () => fireEvent.click(await screen.findByRole("button", { name: "Edit qualification" }));

describe("LeadQualificationForm (tel-009)", () => {
  it("shows the saved values with Not recorded for blanks", async () => {
    getReply = () => res(qual({ study_level: "masters", intake: "Sep 2027", passport_status: "valid" }));
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={() => undefined} />);
    expect(await screen.findByText("Masters")).toBeTruthy();
    expect(screen.getByText("Sep 2027")).toBeTruthy();
    expect(screen.getByText("Has a valid passport")).toBeTruthy();
    expect(screen.getAllByText("Not recorded").length).toBeGreaterThan(0);
    expect(screen.queryByText("Preferred mode")).toBeNull(); // the IT section is hidden for an overseas product
  });

  it("an overseas lead edits basic + overseas fieldsets only and PUTs exactly those fields", async () => {
    const onSaved = vi.fn();
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={onSaved} />);
    await edit();
    expect(screen.getByRole("group", { name: "Basic qualification" })).toBeTruthy();
    const overseas = screen.getByRole("group", { name: "Overseas requirement" });
    expect(screen.queryByRole("group", { name: "IT training requirement" })).toBeNull();
    expect(within(overseas).getByText("UK")).toBeTruthy(); // destination = the lead's product, read-only (QF1)
    fireEvent.change(within(overseas).getByLabelText("UG / Master's"), { target: { value: "masters" } });
    fireEvent.change(within(overseas).getByLabelText("Intake"), { target: { value: " Sep 2027 " } });
    fireEvent.change(within(overseas).getByLabelText("Academic percentage"), { target: { value: "72.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save qualification" }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = JSON.parse(String(puts()[0][1].body));
    expect(body).toMatchObject({ study_level: "masters", intake: "Sep 2027", academic_percentage: 72.5, city: "Chennai", current_org: null });
    expect(body).not.toHaveProperty("preferred_mode");
    expect(await screen.findByText("Qualification saved.")).toBeTruthy();
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ city: "Chennai", qualification: null }));
  });

  it("an IT lead shows the IT section and keeps the hidden overseas values out of the PUT", async () => {
    getReply = () => res(qual({ product: { id: "p-java", name: "Java", group: "it" }, product_group: "it", study_level: "masters" }));
    render(<LeadQualificationForm leadId="L1" productId="p-java" readOnly={false} onSaved={() => undefined} />);
    await edit();
    const it = screen.getByRole("group", { name: "IT training requirement" });
    expect(screen.queryByRole("group", { name: "Overseas requirement" })).toBeNull();
    fireEvent.click(within(it).getByLabelText("Offline"));
    fireEvent.click(screen.getByRole("button", { name: "Save qualification" }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = JSON.parse(String(puts()[0][1].body));
    expect(body.preferred_mode).toBe("offline");
    expect(body).not.toHaveProperty("study_level");
  });

  it("a lead with an Other product (or none) has the basic fields only", async () => {
    getReply = () => res(qual({ product: null, product_group: null }));
    render(<LeadQualificationForm leadId="L1" productId={null} readOnly={false} onSaved={() => undefined} />);
    await edit();
    expect(screen.getByRole("group", { name: "Basic qualification" })).toBeTruthy();
    expect(screen.queryByRole("group", { name: /requirement/ })).toBeNull();
    expect(screen.getByText(/Set the lead's product interest/)).toBeTruthy();
  });

  it("refuses an out-of-range percentage in place, with aria-invalid, and sends nothing", async () => {
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={() => undefined} />);
    await edit();
    const pct = screen.getByLabelText("Academic percentage");
    fireEvent.change(pct, { target: { value: "120" } });
    fireEvent.change(screen.getByLabelText("Passing year"), { target: { value: "1900" } });
    fireEvent.click(screen.getByRole("button", { name: "Save qualification" }));
    expect(await screen.findByText("Enter a percentage from 0 to 100.")).toBeTruthy();
    expect(screen.getByText("Enter a year from 1950 to 2100.")).toBeTruthy();
    expect(pct.getAttribute("aria-invalid")).toBe("true");
    expect(puts()).toHaveLength(0);
  });

  it("shows the server's refusal and stays in the form", async () => {
    putReply = () => res({ detail: "These fields don't apply to this lead's product: preferred_mode" }, 422);
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={() => undefined} />);
    await edit();
    fireEvent.click(screen.getByRole("button", { name: "Save qualification" }));
    expect(await screen.findByText(/don't apply to this lead's product/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save qualification" })).toBeTruthy();
  });

  it("read-only shows the values without an edit button", async () => {
    getReply = () => res(qual({ read_only: true, intake: "Jan 2027" }));
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly onSaved={() => undefined} />);
    expect(await screen.findByText("Jan 2027")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit qualification" })).toBeNull();
  });

  it("a failed load says so and retries", async () => {
    getReply = () => res({ detail: "boom" }, 500);
    render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={() => undefined} />);
    expect(await screen.findByText("Unable to load the qualification.")).toBeTruthy();
    getReply = () => res(qual({ intake: "May 2027" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("May 2027")).toBeTruthy();
  });

  it("re-reads when the lead's product changes (the section follows the saved product)", async () => {
    const { rerender } = render(<LeadQualificationForm leadId="L1" productId="p-uk" readOnly={false} onSaved={() => undefined} />);
    await screen.findByText("Overseas requirement");
    getReply = () => res(qual({ product: { id: "p-java", name: "Java", group: "it" }, product_group: "it" }));
    rerender(<LeadQualificationForm leadId="L1" productId="p-java" readOnly={false} onSaved={() => undefined} />);
    expect(await screen.findByText("IT training requirement")).toBeTruthy();
    expect(screen.queryByText("Overseas requirement")).toBeNull();
  });
});
