import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerProductsPanel from "@/components/TelecallerProductsPanel";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const sap = { id: "p1", group: "it", name: "SAP", team: "it", program: null, active: true, sort_order: 2 };
const guidance = { id: "p2", group: "other", name: "Career Guidance", team: null, program: null, active: true, sort_order: 15 };
const retired = { id: "p3", group: "overseas", name: "Dubai", team: "overseas", program: null, active: false, sort_order: 14 };
const programs = [{ id: "c1", title: "SAP Course" }];

type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return Promise.resolve(handler({ url: String(url), init }));
  }));
  return calls;
}
const listOrPrograms = (list: unknown) => ({ url, init }: Call) =>
  url.includes("/public/programs") ? res(programs) : init?.method ? res({}) : res(list);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TelecallerProductsPanel (tel-002)", () => {
  it("lists products with group, team and status; an inactive one is labelled", async () => {
    serve(listOrPrograms(page([sap, guidance, retired])));
    render(<TelecallerProductsPanel />);
    const row = (await screen.findByText("Career Guidance")).closest("tr")!;
    expect(within(row).getByText("Unassigned queue")).toBeInTheDocument();
    expect(within(screen.getByText("Dubai").closest("tr")!).getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Products" })).toBeInTheDocument();
  });

  it("shows the empty state and the load error with Retry", async () => {
    serve(listOrPrograms(page([])));
    render(<TelecallerProductsPanel />);
    expect(await screen.findByText("No products yet.")).toBeInTheDocument();
    cleanup();
    serve(({ url }) => (url.includes("/public/programs") ? res(programs) : res({ detail: "x" }, 500)));
    render(<TelecallerProductsPanel />);
    expect(await screen.findByText("Unable to load products.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("asks for a team only for an Other product, and a course only for an IT product", async () => {
    serve(listOrPrograms(page([])));
    render(<TelecallerProductsPanel />);
    const group = screen.getByLabelText("Group (required)");
    expect(screen.queryByLabelText("Team")).not.toBeInTheDocument();
    expect(await screen.findByLabelText("Linked IT course")).toBeInTheDocument();
    fireEvent.change(group, { target: { value: "other" } });
    expect(screen.getByLabelText("Team")).toBeInTheDocument();
    expect(screen.queryByLabelText("Linked IT course")).not.toBeInTheDocument();
    fireEvent.change(group, { target: { value: "overseas" } });
    expect(screen.queryByLabelText("Team")).not.toBeInTheDocument();
    expect(screen.getByText(/Overseas products route to the Overseas team/)).toBeInTheDocument();
  });

  it("creates an Other product with its team and reports success", async () => {
    const calls = serve(({ url, init }) => (url.includes("/public/programs") ? res(programs) : init?.method === "POST" ? res({ ...guidance, id: "new" }, 201) : res(page([]))));
    render(<TelecallerProductsPanel />);
    fireEvent.change(screen.getByLabelText("Group (required)"), { target: { value: "other" } });
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "  Career Coaching " } });
    fireEvent.change(screen.getByLabelText("Team"), { target: { value: "it" } });
    fireEvent.click(screen.getByRole("button", { name: "Create product" }));
    expect(await screen.findByText("Created Career Coaching.")).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(post.init!.body))).toEqual({ group: "other", name: "Career Coaching", team: "it" });
  });

  it("shows the server's sentence when create fails and keeps the entry", async () => {
    serve(({ url, init }) => (url.includes("/public/programs") ? res(programs) : init?.method === "POST" ? res({ detail: "A product named “SAP” already exists in this group" }, 409) : res(page([]))));
    render(<TelecallerProductsPanel />);
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "SAP" } });
    fireEvent.click(screen.getByRole("button", { name: "Create product" }));
    expect(await screen.findByText("A product named “SAP” already exists in this group")).toBeInTheDocument();
    expect(screen.getByLabelText("Name (required)")).toHaveValue("SAP");
  });

  it("edits a row inline (Esc cancels) and PATCHes only the editable fields", async () => {
    const calls = serve(listOrPrograms(page([guidance])));
    render(<TelecallerProductsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Career Guidance" }));
    fireEvent.keyDown(screen.getByLabelText("Product name (required)"), { key: "Escape" });
    expect(screen.queryByLabelText("Product name (required)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit Career Guidance" }));
    fireEvent.change(screen.getByLabelText("Product name (required)"), { target: { value: "Guidance" } });
    fireEvent.change(screen.getByLabelText("Product team"), { target: { value: "overseas" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved Guidance.")).toBeInTheDocument();
    const patch = calls.find((c) => c.init?.method === "PATCH")!;
    expect(patch.url).toContain("/telecaller/products/p2");
    expect(JSON.parse(String(patch.init!.body))).toEqual({ name: "Guidance", team: "overseas", sort_order: 15 });
  });

  it("deactivates only after an inline confirm", async () => {
    const calls = serve(listOrPrograms(page([sap])));
    render(<TelecallerProductsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate SAP" }));
    expect(calls.some((c) => c.init?.method === "PATCH")).toBe(false);
    expect(screen.getByText(/disappears from pickers/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Deactivated SAP.")).toBeInTheDocument();
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body))).toEqual({ active: false });
  });
});
