import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import { USERS_CHANGED } from "@/lib/usersChanged";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managerPage = { items: [{ id: "m1", full_name: "Meera", email: "meera@x.local" }, { id: "m2", full_name: "Meera", email: "meera.k@x.local" }], total: 2, limit: 20, offset: 0 };

/** Picker searches go to /admin/bdm-managers; anything else (the create POST) gets `post`. */
function route(post: Response | Error) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    if (String(url).startsWith("/api/v1/admin/bdm-managers")) return Promise.resolve(res(managerPage));
    return post instanceof Error ? Promise.reject(post) : Promise.resolve(post);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function pickManager(text = "meera.k") {
  const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: text } });
  fireEvent.click(await screen.findByRole("option", { name: "Meera — meera.k@x.local" }));
}

async function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Asha" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "asha@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "E-9" } });
  await pickManager();
}

describe("AdminBdmCreateForm (bdm-001 AC01, AC13, QA-02, QA-03)", () => {
  it("offers only the types the admin may create", () => {
    route(res({}));
    render(<AdminBdmCreateForm role="overseas_admin" managersAvailable onCreated={() => {}} />);
    const select = screen.getByLabelText("Module (required)");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual(["Agent", "School"]);
  });

  it("shows a single creatable type as fixed text, not a one-option select", () => {
    route(res({}));
    render(<AdminBdmCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    expect(screen.queryByLabelText("Module (required)")).toBeNull();
    expect(screen.getByText("College")).toBeInTheDocument();
  });

  it("explains and disables submit when there is no active manager", () => {
    route(res({}));
    render(<AdminBdmCreateForm role="super_admin" managersAvailable={false} onCreated={() => {}} />);
    expect(screen.getByText("No active BDM manager — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create BDM" })).toBeDisabled();
  });

  it("searches managers on the server and tells same-name managers apart by email (QA-02, QA-03)", async () => {
    const mock = route(res({}));
    render(<AdminBdmCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
    fireEvent.focus(combo);
    fireEvent.change(combo, { target: { value: "meera" } });
    expect(await screen.findByRole("option", { name: "Meera — meera@x.local" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Meera — meera.k@x.local" })).toBeInTheDocument();
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/admin/bdm-managers?limit=20&q=meera")).toBe(true);
  });

  it("posts the nested profile with the picked manager, shows link feedback, announces and reports the Employee ID", async () => {
    const mock = route(res({ id: "b9", email_status: "sent", bdm_profile: {} }, 201));
    const announced = vi.fn();
    window.addEventListener(USERS_CHANGED, announced);
    const onCreated = vi.fn();
    render(<AdminBdmCreateForm role="it_admin" managersAvailable onCreated={onCreated} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/set-password link was emailed/)).toBeInTheDocument();
    const post = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users")!;
    expect(JSON.parse(String(post[1]?.body))).toEqual({
      role: "bdm", full_name: "Asha", email: "asha@x.local", phone: null,
      bdm_profile: { bdm_type: "college", employee_id: "E-9", designation: null, department: null, territory: null, reporting_manager_user_id: "m2" },
    });
    expect(announced).toHaveBeenCalled();
    expect(onCreated).toHaveBeenCalledWith("E-9");
    window.removeEventListener(USERS_CHANGED, announced);
  });

  it("shows a 409 inline, moves focus to it and keeps the entry", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    render(<AdminBdmCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    const message = await screen.findByText("Employee ID already exists");
    await waitFor(() => expect(message).toHaveFocus());
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("E-9");
  });

  it("keeps the entry and says so on a network failure", async () => {
    route(new TypeError("offline"));
    render(<AdminBdmCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/your entry is kept/)).toBeInTheDocument();
    expect(screen.getByLabelText("Full name (required)")).toHaveValue("Asha");
  });
});
