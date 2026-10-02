import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import { USERS_CHANGED } from "@/lib/usersChanged";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managers = [{ id: "m1", full_name: "Meera" }];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Asha" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "asha@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "E-9" } });
  fireEvent.change(screen.getByLabelText("Reporting manager (required)"), { target: { value: "m1" } });
}

describe("AdminBdmCreateForm (bdm-001 AC01, AC13)", () => {
  it("offers only the types the admin may create", () => {
    render(<AdminBdmCreateForm role="overseas_admin" managers={managers} onCreated={() => {}} />);
    const select = screen.getByLabelText("Module (required)");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual(["Agent", "School"]);
  });

  it("shows a single creatable type as fixed text, not a one-option select", () => {
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    expect(screen.queryByLabelText("Module (required)")).toBeNull();
    expect(screen.getByText("College")).toBeInTheDocument();
  });

  it("explains and disables submit when there is no active manager", () => {
    render(<AdminBdmCreateForm role="super_admin" managers={[]} onCreated={() => {}} />);
    expect(screen.getByText("No active BDM manager — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create BDM" })).toBeDisabled();
  });

  it("posts the nested profile with no password, shows the link feedback and announces the change", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ id: "b9", email_status: "sent", bdm_profile: {} }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const announced = vi.fn();
    window.addEventListener(USERS_CHANGED, announced);
    const onCreated = vi.fn();
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/set-password link was emailed/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/admin/users");
    const body = JSON.parse(init.body);
    expect(body).toEqual({
      role: "bdm", full_name: "Asha", email: "asha@x.local", phone: null,
      bdm_profile: { bdm_type: "college", employee_id: "E-9", designation: null, department: null, territory: null, reporting_manager_user_id: "m1" },
    });
    expect(announced).toHaveBeenCalled();
    expect(onCreated).toHaveBeenCalled();
    window.removeEventListener(USERS_CHANGED, announced);
  });

  it("shows a 409 inline, moves focus to it and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409)));
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    const message = await screen.findByText("Employee ID already exists");
    await waitFor(() => expect(message).toHaveFocus());
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("E-9");
  });

  it("keeps the entry and says so on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/your entry is kept/)).toBeInTheDocument();
    expect(screen.getByLabelText("Full name (required)")).toHaveValue("Asha");
  });
});
