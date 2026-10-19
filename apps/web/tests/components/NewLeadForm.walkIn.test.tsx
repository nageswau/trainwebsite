import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewLeadForm from "@/components/NewLeadForm";
import { WALK_IN_LEADS_URL } from "@/lib/leadHandover";

const CHECK = `${WALK_IN_LEADS_URL}/duplicate-check`;

// csc-004 (DEC-SCOPE-229): the overseas counselor's walk-in lead uses the tel-005 form with its own endpoints, the source preset to
// Walk-in and the division fixed to Overseas (no Division picker, no IT-team products).
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const products = pageOf([
  { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 },
  { id: "p2", group: "overseas", name: "MS in Germany", team: "overseas", program: null, active: true, sort_order: 2 },
  { id: "p3", group: "other", name: "Spoken English", team: null, program: null, active: true, sort_order: 3 },
]);

let fetchMock: ReturnType<typeof vi.fn>;
const calls = (method: string, path: string) => fetchMock.mock.calls.filter(([url, init]) => (init?.method ?? "GET") === method && String(url).startsWith(path));

beforeEach(() => {
  push.mockReset();
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(pageOf([])));
    if (url.startsWith(CHECK)) return Promise.resolve(res({ matches: [] }));
    if (method === "POST" && url === WALK_IN_LEADS_URL) return Promise.resolve(res({ id: "NEW1", lead_code: "LD-000100", in_scope: true }, 201));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

function renderWalkIn() {
  render(<NewLeadForm basePath="/overseas/counselor/leads" apiBase={WALK_IN_LEADS_URL} initial={{ source: "walk_in" }} team="overseas" />);
}

describe("NewLeadForm for a counselor's walk-in lead (csc-004)", () => {
  it("presets the source to Walk-in and offers only Overseas and team-less products", async () => {
    renderWalkIn();
    await screen.findByRole("option", { name: "MS in Germany" });
    expect((screen.getByLabelText(/Lead source/) as HTMLSelectElement).value).toBe("walk_in");
    expect(screen.queryByRole("option", { name: "Cyber Security" })).toBeNull();
    expect(screen.getByRole("option", { name: "Spoken English" })).toBeInTheDocument();
  });

  it("never asks for the division, even for a team-less product, and posts to the counselor's endpoint", async () => {
    renderWalkIn();
    await screen.findByRole("option", { name: "Spoken English" });
    type(/Student name/, "Walk-in Student");
    type(/Mobile number/, "98765 43210");
    type(/Product interest/, "p3");
    expect(screen.queryByLabelText(/Division/)).toBeNull();
    fireEvent.blur(screen.getByLabelText(/Mobile number/));
    await waitFor(() => expect(calls("GET", CHECK)).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/counselor/leads/NEW1"));
    const sent = JSON.parse(String(calls("POST", WALK_IN_LEADS_URL)[0][1].body));
    expect(sent).toMatchObject({ name: "Walk-in Student", phone: "98765 43210", product_id: "p3", source: "walk_in", division: "overseas" });
    expect(calls("POST", "/api/v1/telecaller/leads")).toHaveLength(0);
  });
});
