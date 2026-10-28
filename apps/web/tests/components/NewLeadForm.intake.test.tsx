import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewLeadForm from "@/components/NewLeadForm";

// ccrm-047: an overseas-study lead takes its intake (month + year) at creation; an IT lead has no intake field.
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const products = pageOf([
  { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 },
  { id: "p3", group: "overseas", name: "UK", team: "overseas", program: null, active: true, sort_order: 3 },
]);
const YEAR = String(new Date().getFullYear() + 1);

let fetchMock: ReturnType<typeof vi.fn>;
const creates = () => fetchMock.mock.calls.filter(([url, init]) => init?.method === "POST" && url === "/api/v1/telecaller/leads");

beforeEach(() => {
  push.mockReset();
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(pageOf([])));
    if (init?.method === "POST") return Promise.resolve(res({ id: "NEW1", lead_code: "LD-000100" }, 201));
    return Promise.resolve(res({ matches: [] }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function fill(productId: string) {
  render(<NewLeadForm basePath="/telecaller/leads" />);
  await screen.findByRole("option", { name: "UK" });
  type(/Student name/, "Asha Rao");
  type(/Mobile number/, "98765 43210");
  type(/Product interest/, productId);
  type(/Lead source/, "instagram");
}

describe("NewLeadForm intake (ccrm-047)", () => {
  it("sends the chosen intake for an overseas lead", async () => {
    await fill("p3");
    type("Intake month", "Sep");
    type("Intake year", YEAR);
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/telecaller/leads/NEW1"));
    expect(JSON.parse(String(creates()[0][1]!.body)).intake).toBe(`Sep ${YEAR}`);
  });

  it("refuses a half-chosen intake and sends nothing", async () => {
    await fill("p3");
    type("Intake month", "Sep");
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    expect(await screen.findByText("Choose both the month and the year for the intake.")).toBeInTheDocument();
    expect(creates()).toHaveLength(0);
  });

  it("has no intake for an IT lead, and switching product drops a chosen intake", async () => {
    await fill("p3");
    type("Intake month", "Sep");
    type("Intake year", YEAR);
    type(/Product interest/, "p1");
    expect(screen.queryByLabelText("Intake month")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(creates()).toHaveLength(1));
    expect(JSON.parse(String(creates()[0][1]!.body))).not.toHaveProperty("intake");
  });
});
