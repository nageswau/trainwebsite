import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DataTable from "@/components/DataTable";

// csc-005 (DEC-SCOPE-230): the Overseas Admin's Users directory moves an overseas student to another counselor with AGN-023's picker,
// declared by the server as `assign_student_counselor`; it saves to PUT /admin/users/{id}/counselor. Staff rows (assign null) get none.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const PAGE = { items: [{ id: "c2", label: "Neha Counselor", detail: null }], truncated: false };

function table() {
  render(
    <DataTable
      columns={[{ key: "name", label: "Name" }, { key: "counselor", label: "EduSphere counsellor" }, { key: "assign", label: "", type: "assign_student_counselor" }]}
      rows={[
        { id: "s1", name: "Walk-in Student", counselor: "Old Counselor", counselor_id: "c1", assign: "s1" },
        { id: "s2", name: "New Student", counselor: "Not assigned", counselor_id: null, assign: "s2" },
        { id: "u1", name: "Staff Member", counselor: null, counselor_id: null, assign: null },
      ]}
      label="Users"
    />,
  );
}

describe("DataTable assign_student_counselor column (csc-005)", () => {
  it("offers Change or Assign counsellor on student rows and nothing on staff rows", () => {
    vi.stubGlobal("fetch", vi.fn());
    table();
    expect(within(screen.getByText("Walk-in Student").closest("tr") as HTMLElement).getByRole("button", { name: "Change counsellor" })).toBeTruthy();
    expect(within(screen.getByText("New Student").closest("tr") as HTMLElement).getByRole("button", { name: "Assign counsellor" })).toBeTruthy();
    expect(within(screen.getByText("Staff Member").closest("tr") as HTMLElement).queryByRole("button")).toBeNull();
  });

  it("saves to the student's counselor route", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json(200, { id: "s1", counselor_id: "c2", counselor_name: "Neha Counselor", changed: true }) : json(200, PAGE),
    );
    vi.stubGlobal("fetch", fetchMock);
    table();
    fireEvent.click(within(screen.getByText("Walk-in Student").closest("tr") as HTMLElement).getByRole("button", { name: "Change counsellor" }));
    fireEvent.change(await screen.findByRole("combobox", { name: "EduSphere counsellor" }), { target: { value: "Neha" } });
    fireEvent.click(await screen.findByRole("option", { name: /Neha Counselor/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for the change" }), { target: { value: "Student request" } }); // ccrm-033 RR1
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Neha Counselor assigned.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/users/s1/counselor",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c2", reason: "Student request" }) }));
    expect(refresh).toHaveBeenCalled();
  });
});
