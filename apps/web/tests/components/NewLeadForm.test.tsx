import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewLeadForm from "@/components/NewLeadForm";
import type { DuplicateMatch } from "@/lib/telecallerLeads";

// tel-005 (spec §4; I1, I5, R2, R5): the New Lead form, its duplicate panel and "Add enquiry to this lead".
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const products = pageOf([
  { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 },
  { id: "p2", group: "other", name: "Spoken English", team: null, program: null, active: true, sort_order: 2 },
]);
const campaigns = pageOf([
  { id: "c1", name: "Sep Instagram", source: "instagram", product: { id: "p1", name: "Cyber Security", group: "it", active: true }, start_date: "2026-09-01", end_date: null, active: true },
  { id: "c2", name: "English Fair", source: "exhibition_event", product: { id: "p2", name: "Spoken English", group: "other", active: true }, start_date: "2026-09-01", end_date: null, active: true },
]);
const match = (over: Partial<DuplicateMatch> = {}): DuplicateMatch => ({
  id: "L9", lead_code: "LD-000009", name: "Rahul K", status: "not_interested", status_label: "Not Interested",
  telecaller: { id: "t2", full_name: "Other Caller" }, counselor: null, last_contact_at: null, matched_on: ["phone"],
  enquiries: [{ subject: "Python", source: "website", at: "2026-09-02T05:00:00Z" }], in_scope: false, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
let createReply: () => Response;
let checkReply: () => Response;
const calls = (method: string, path: string) => fetchMock.mock.calls.filter(([url, init]) => (init?.method ?? "GET") === method && String(url).startsWith(path));
const body = (method: string, path: string) => JSON.parse(String(calls(method, path).at(-1)?.[1]?.body));

beforeEach(() => {
  push.mockReset();
  createReply = () => res({ id: "NEW1", lead_code: "LD-000100" }, 201);
  checkReply = () => res({ matches: [] });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(campaigns));
    if (url.startsWith("/api/v1/telecaller/leads/duplicate-check")) return Promise.resolve(checkReply());
    if (method === "POST" && url === "/api/v1/telecaller/leads") return Promise.resolve(createReply());
    if (method === "POST" && url.endsWith("/enquiries")) return Promise.resolve(res({ id: "E1", lead_id: "L9", lead_code: "LD-000009", subject: "x", source: "instagram", created_at: "x" }, 201));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function fillRequired() {
  render(<NewLeadForm basePath="/telecaller/leads" />);
  await screen.findByRole("option", { name: "Cyber Security" });
  type(/Student name/, "Rahul Kumar");
  type(/Mobile number/, "98765 43210");
  type(/Product interest/, "p1");
  type(/Lead source/, "instagram");
}

describe("NewLeadForm (tel-005)", () => {
  it("creates a lead with only the filled fields and opens it", async () => {
    await fillRequired();
    type(/City/, "Pune");
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/telecaller/leads/NEW1"));
    expect(body("POST", "/api/v1/telecaller/leads")).toEqual({
      name: "Rahul Kumar", phone: "98765 43210", product_id: "p1", source: "instagram", priority: "warm", city: "Pune",
    });
  });

  it("lists only the product's campaigns, and a campaign sets the source", async () => {
    await fillRequired();
    const campaign = screen.getByLabelText(/Campaign/);
    expect(within(campaign).queryByRole("option", { name: "English Fair" })).toBeNull();
    type(/Lead source/, "google");
    type(/Campaign/, "c1");
    expect((screen.getByLabelText(/Lead source/) as HTMLSelectElement).value).toBe("instagram");
  });

  it("asks for the division only for a product without a team", async () => {
    await fillRequired();
    expect(screen.queryByLabelText(/Division/)).toBeNull();
    type(/Product interest/, "p2");
    type(/Division/, "overseas");
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(body("POST", "/api/v1/telecaller/leads")).toMatchObject({ product_id: "p2", division: "overseas" }));
  });

  it("shows the duplicate panel on a 409 and adds the enquiry to the existing lead", async () => {
    createReply = () => res({ detail: { message: "Lead already exists.", code: "duplicate_lead", matches: [match()] } }, 409);
    await fillRequired();
    type(/Enquiry subject/, "Weekend batch");
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    const panel = await screen.findByRole("region", { name: /Lead already exists/ });
    for (const text of ["LD-000009", "Rahul K", "Not Interested", "Other Caller", "Not assigned", "No contact logged yet", "Python"]) {
      expect(within(panel).getAllByText(text, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(within(panel).queryByRole("link", { name: /Open/ })).toBeNull(); // not in the caller's scope
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(within(panel).getByRole("button", { name: "Add enquiry to LD-000009" }));
    expect(await within(panel).findByText("Enquiry added to LD-000009.")).toBeTruthy();
    expect(calls("POST", "/api/v1/telecaller/leads/L9/enquiries")).toHaveLength(1);
    expect(body("POST", "/api/v1/telecaller/leads/L9/enquiries")).toEqual({ subject: "Weekend batch", source: "instagram" });
  });

  it("checks for duplicates when the mobile number is left, and links a lead in scope", async () => {
    checkReply = () => res({ matches: [match({ in_scope: true, matched_on: ["phone", "email"] })] });
    await fillRequired();
    fireEvent.blur(screen.getByLabelText(/Mobile number/));
    const panel = await screen.findByRole("region", { name: /Lead already exists/ });
    expect(calls("GET", "/api/v1/telecaller/leads/duplicate-check?phone=98765+43210")).toHaveLength(1);
    expect(within(panel).getByRole("link", { name: "Open LD-000009" }).getAttribute("href")).toBe("/telecaller/leads/L9");
  });

  it("QA-02: names the missing required fields and sends nothing", async () => {
    render(<NewLeadForm basePath="/telecaller/leads" />);
    await screen.findByRole("option", { name: "Cyber Security" });
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    expect((await screen.findByText("Enter the student name, mobile number, product interest and lead source.")).getAttribute("role")).toBe("alert");
    expect(calls("POST", "/api/v1/telecaller/leads")).toHaveLength(0);
  });

  it("QA-03: clears the panel when the mobile no longer matches or can't be checked", async () => {
    checkReply = () => res({ matches: [match()] });
    await fillRequired();
    fireEvent.blur(screen.getByLabelText(/Mobile number/));
    await screen.findByRole("region", { name: /Lead already exists/ });
    checkReply = () => res({ detail: "Enter a valid mobile number" }, 422);
    type(/Mobile number/, "12");
    fireEvent.blur(screen.getByLabelText(/Mobile number/));
    await waitFor(() => expect(screen.queryByRole("region", { name: /Lead already exists/ })).toBeNull());
  });

  it("QA-04: a double click adds one enquiry and the button then says it is done; Create is sent once", async () => {
    createReply = () => res({ detail: { message: "Lead already exists.", code: "duplicate_lead", matches: [match()] } }, 409);
    await fillRequired();
    const create = screen.getByRole("button", { name: "Create lead" });
    fireEvent.click(create);
    fireEvent.click(create);
    const panel = await screen.findByRole("region", { name: /Lead already exists/ });
    expect(calls("POST", "/api/v1/telecaller/leads")).toHaveLength(1);
    const add = within(panel).getByRole("button", { name: "Add enquiry to LD-000009" });
    fireEvent.click(add);
    fireEvent.click(add);
    await within(panel).findByText("Enquiry added to LD-000009.");
    expect(calls("POST", "/api/v1/telecaller/leads/L9/enquiries")).toHaveLength(1);
    expect((within(panel).getByRole("button", { name: "Add enquiry to LD-000009" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(panel).getByRole("button", { name: "Add enquiry to LD-000009" }).textContent).toBe("Enquiry added");
  });

  it("QA-05: the panel comes before the form, and a refused create moves focus to it", async () => {
    createReply = () => res({ detail: { message: "Lead already exists.", code: "duplicate_lead", matches: [match()] } }, 409);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    const heading = await screen.findByRole("heading", { name: /Lead already exists/ });
    const form = screen.getByRole("button", { name: "Create lead" }).closest("form")!;
    expect(heading.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  it("QA-01: priority options are short and the chosen level's help shows beside them", async () => {
    render(<NewLeadForm basePath="/telecaller/leads" />);
    const priority = screen.getByLabelText("Priority");
    expect(within(priority).getAllByRole("option").map((o) => o.textContent)).toEqual(["Hot", "Warm", "Cold"]);
    expect(screen.getByText("Interested but needs follow-up.")).toBeTruthy();
    fireEvent.change(priority, { target: { value: "hot" } });
    expect(screen.getByText("Ready to join / immediate requirement.")).toBeTruthy();
  });

  it("QA-06: a lead that went to someone outside the caller's leads is confirmed in place, not opened", async () => {
    createReply = () => res({ id: "NEW2", lead_code: "LD-000200", in_scope: false, telecaller: { id: "t9", full_name: "Far Caller" } }, 201);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    expect((await screen.findByText("Lead LD-000200 created and assigned to Far Caller.")).getAttribute("role")).toBe("status");
    expect(push).not.toHaveBeenCalled();
    expect((screen.getByLabelText(/Student name/) as HTMLInputElement).value).toBe(""); // ready for the next caller
  });

  it("shows the API's message when the lead is refused", async () => {
    createReply = () => res({ detail: "This campaign is for another product" }, 422);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    expect((await screen.findByText("This campaign is for another product")).getAttribute("role")).toBe("alert");
  });
});
