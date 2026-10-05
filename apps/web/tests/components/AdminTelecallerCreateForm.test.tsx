import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerCreateForm from "@/components/AdminTelecallerCreateForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managerPage = { items: [{ id: "m1", full_name: "Meena", email: "meena@x.local" }, { id: "m2", full_name: "Meena", email: "meena.k@x.local" }], total: 2, limit: 20, offset: 0 };

function route(post: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).startsWith("/api/v1/admin/telecaller-managers") ? res(managerPage) : post));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Ravi" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "ravi@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "T-9" } });
  const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "meena.k" } });
  fireEvent.click(await screen.findByRole("option", { name: "Meena — meena.k@x.local" }));
}

describe("AdminTelecallerCreateForm (tel-001 AC1, AC2)", () => {
  it("lets a super admin choose the team", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="super_admin" managersAvailable onCreated={() => {}} />);
    const select = screen.getByLabelText("Team (required)");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual(["IT", "Overseas"]);
  });

  it("shows a division admin's only team as fixed text", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="overseas_admin" managersAvailable onCreated={() => {}} />);
    expect(screen.queryByLabelText("Team (required)")).toBeNull();
    expect(screen.getByText("Overseas")).toBeInTheDocument();
  });

  it("explains and disables submit when there is no active manager", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="super_admin" managersAvailable={false} onCreated={() => {}} />);
    expect(screen.getByText("No active telecaller manager — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create telecaller" })).toBeDisabled();
  });

  it("POSTs role + nested profile and reports the welcome link", async () => {
    const mock = route(res({ id: "b9", email_status: "sent", telecaller_profile: {} }, 201));
    const onCreated = vi.fn();
    render(<AdminTelecallerCreateForm role="it_admin" managersAvailable onCreated={onCreated} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create telecaller" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("T-9"));
    expect(screen.getByRole("status")).toHaveTextContent("Telecaller created. A set-password link was emailed and is valid for 72 hours.");
    const post = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      role: "telecaller", full_name: "Ravi", email: "ravi@x.local", phone: null,
      telecaller_profile: { team: "it", employee_id: "T-9", reporting_manager_user_id: "m2" },
    });
  });

  it("keeps the typed values and shows the server's message on 409", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    render(<AdminTelecallerCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create telecaller" }));
    expect(await screen.findByText("Employee ID already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("T-9");
  });
});
