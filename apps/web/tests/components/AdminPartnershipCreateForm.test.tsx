import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminPartnershipCreateForm from "@/components/AdminPartnershipCreateForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const headPage = { items: [{ id: "h1", full_name: "Hema", email: "hema@x.local" }, { id: "h2", full_name: "Hema", email: "hema.k@x.local" }], total: 2, limit: 20, offset: 0 };

function route(post: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).startsWith("/api/v1/admin/partnership-heads") ? res(headPage) : post));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Rahul" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "rahul@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "P-9" } });
  const combo = screen.getByRole("combobox", { name: "Reporting head (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "hema.k" } });
  fireEvent.click(await screen.findByRole("option", { name: "Hema — hema.k@x.local" }));
}

describe("AdminPartnershipCreateForm (upc-001 AC1)", () => {
  it("explains and disables submit when there is no active head", () => {
    route(res({}));
    render(<AdminPartnershipCreateForm headsAvailable={false} onCreated={() => {}} />);
    expect(screen.getByText("No active partnership head — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create partnership manager" })).toBeDisabled();
  });

  it("POSTs role + nested profile and reports the welcome link", async () => {
    const mock = route(res({ id: "p9", email_status: "sent", partnership_profile: {} }, 201));
    const onCreated = vi.fn();
    render(<AdminPartnershipCreateForm headsAvailable onCreated={onCreated} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create partnership manager" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("P-9"));
    expect(screen.getByRole("status")).toHaveTextContent("Partnership manager created. A set-password link was emailed and is valid for 72 hours.");
    const post = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      role: "partnership_manager", full_name: "Rahul", email: "rahul@x.local", phone: null,
      partnership_profile: { employee_id: "P-9", reporting_head_user_id: "h2" },
    });
  });

  it("keeps the typed values and shows the server's message on 409", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    const onCreated = vi.fn();
    render(<AdminPartnershipCreateForm headsAvailable onCreated={onCreated} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create partnership manager" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Employee ID already exists"));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("P-9");
  });

  it("sends one POST on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const mock = vi.fn((url: string) => (String(url).startsWith("/api/v1/admin/partnership-heads") ? Promise.resolve(res(headPage)) : new Promise<Response>((r) => { resolve = r; })));
    vi.stubGlobal("fetch", mock);
    render(<AdminPartnershipCreateForm headsAvailable onCreated={() => {}} />);
    await fill();
    const button = screen.getByRole("button", { name: "Create partnership manager" });
    fireEvent.click(button);
    fireEvent.click(button);
    resolve(res({ id: "p9" }, 201));
    await waitFor(() => expect(mock.mock.calls.filter(([url]) => url === "/api/v1/admin/users")).toHaveLength(1));
  });
});
