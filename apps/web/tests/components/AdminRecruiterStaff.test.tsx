import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminRecruiterCreateForm from "@/components/AdminRecruiterCreateForm";
import AdminRecruiterRow from "@/components/AdminRecruiterRow";
import type { RecruiterAdminRow } from "@/lib/recruiter";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managerPage = { items: [{ id: "m1", full_name: "Nisha", email: "nisha@x.local" }], total: 1, limit: 20, offset: 0 };

function route(write: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).startsWith("/api/v1/admin/placement-managers") ? res(managerPage) : write));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function pickManager() {
  const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "nis" } });
  fireEvent.click(await screen.findByRole("option", { name: "Nisha — nisha@x.local" }));
}

describe("AdminRecruiterCreateForm (rec-001 AC1)", () => {
  it("explains and disables submit when there is no active placement manager", () => {
    route(res({}));
    render(<AdminRecruiterCreateForm managersAvailable={false} onCreated={() => {}} />);
    expect(screen.getByText("No active placement manager — a Super Admin must create one first (Users → Placement Manager).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create recruiter" })).toBeDisabled();
  });

  it("POSTs the recruiter with the nested profile and reports the welcome link", async () => {
    const mock = route(res({ id: "r9", email_status: "sent", recruiter_profile: {} }, 201));
    const onCreated = vi.fn();
    render(<AdminRecruiterCreateForm managersAvailable onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Priya" } });
    fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "priya@x.local" } });
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: " R-9 " } });
    await pickManager();
    fireEvent.click(screen.getByRole("button", { name: "Create recruiter" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("R-9"));
    const post = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      role: "placement_team", full_name: "Priya", email: "priya@x.local", phone: null,
      recruiter_profile: { employee_id: "R-9", reporting_manager_user_id: "m1" },
    });
    expect(screen.getByRole("status")).toHaveTextContent("Recruiter created.");
  });

  it("keeps what was typed and shows the server's message on a refusal", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    render(<AdminRecruiterCreateForm managersAvailable onCreated={() => {}} />);
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Priya" } });
    fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "priya@x.local" } });
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "R-1" } });
    await pickManager();
    fireEvent.click(screen.getByRole("button", { name: "Create recruiter" }));
    expect(await screen.findByText("Employee ID already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("R-1");
  });
});

const row = (over: Partial<RecruiterAdminRow> = {}): RecruiterAdminRow => ({
  id: "r1", full_name: "Kiran", email: "kiran@x.local", phone: null, active: true, employee_id: "R-1",
  reporting_manager: { id: "m1", full_name: "Nisha", active: true }, ...over,
});

function table(ui: React.ReactNode) {
  return render(<table><tbody>{ui}</tbody></table>);
}

describe("AdminRecruiterRow (rec-001 AC5)", () => {
  it("flags a recruiter with no manager and no Employee ID", () => {
    table(<AdminRecruiterRow row={row({ employee_id: null, reporting_manager: null })} onChanged={() => {}} />);
    expect(screen.getByText("No manager")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("flags an inactive manager", () => {
    table(<AdminRecruiterRow row={row({ reporting_manager: { id: "m1", full_name: "Nisha", active: false } })} onChanged={() => {}} />);
    expect(screen.getByText("Nisha")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
  });

  it("sets a manager on a backfilled recruiter", async () => {
    const mock = route(res({ ok: true }));
    const onChanged = vi.fn();
    table(<AdminRecruiterRow row={row({ employee_id: null, reporting_manager: null })} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Kiran" }));
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "R-7" } });
    await pickManager();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Kiran."));
    const patch = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users/r1")!;
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ full_name: "Kiran", phone: null, recruiter_profile: { employee_id: "R-7", reporting_manager_user_id: "m1" } });
  });

  it("deactivates and reactivates through the users route", async () => {
    const mock = route(res({ ok: true }));
    const onChanged = vi.fn();
    table(<AdminRecruiterRow row={row()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Kiran" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Kiran."));
    expect(JSON.parse(String(mock.mock.calls.at(-1)![1]!.body))).toEqual({ active: false });
    cleanup();
    table(<AdminRecruiterRow row={row({ active: false })} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Kiran" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Reactivated Kiran."));
  });

  it("shows a refusal from the server and keeps the edit open", async () => {
    route(res({ detail: "Reporting manager must be an active placement manager" }, 422));
    table(<AdminRecruiterRow row={row()} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Kiran" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reporting manager must be an active placement manager");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
