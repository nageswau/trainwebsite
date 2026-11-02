import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DataTable from "@/components/DataTable";

// itc-003 (DEC-SCOPE-337): the IT Admin's Students page moves an IT student to another IT counselor with csc-005's picker, declared by
// the server as `assign_it_student_counselor`; it searches the IT counselors and saves to PUT /admin/it/students/{id}/counselor.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const PAGE = { items: [{ id: "c2", label: "Ravi Counselor", detail: null }], truncated: false };

function table() {
  render(
    <DataTable
      columns={[{ key: "name", label: "Name" }, { key: "counselor", label: "EduSphere counsellor" }, { key: "assign", label: "", type: "assign_it_student_counselor" }]}
      rows={[
        { id: "s1", name: "IT Student", counselor: "Old Counselor", counselor_id: "c1", assign: "s1" },
        { id: "s2", name: "New IT Student", counselor: "Not assigned", counselor_id: null, assign: "s2" },
      ]}
      label="Students"
    />,
  );
}

describe("DataTable assign_it_student_counselor column (itc-003)", () => {
  it("offers Change or Assign counsellor", () => {
    vi.stubGlobal("fetch", vi.fn());
    table();
    expect(within(screen.getByText("IT Student").closest("tr") as HTMLElement).getByRole("button", { name: "Change counsellor" })).toBeTruthy();
    expect(within(screen.getByText("New IT Student").closest("tr") as HTMLElement).getByRole("button", { name: "Assign counsellor" })).toBeTruthy();
  });

  it("searches IT counselors and saves to the IT student's counselor route", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json(200, { id: "s1", counselor_id: "c2", counselor_name: "Ravi Counselor", changed: true }) : json(200, PAGE),
    );
    vi.stubGlobal("fetch", fetchMock);
    table();
    fireEvent.click(within(screen.getByText("IT Student").closest("tr") as HTMLElement).getByRole("button", { name: "Change counsellor" }));
    fireEvent.change(await screen.findByRole("combobox", { name: "EduSphere counsellor" }), { target: { value: "Ravi" } });
    fireEvent.click(await screen.findByRole("option", { name: /Ravi Counselor/ }));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/lookups/it-counselors?");
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for the change" }), { target: { value: "Workload" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Ravi Counselor assigned.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/it/students/s1/counselor",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c2", reason: "Workload" }) }));
    expect(refresh).toHaveBeenCalled();
  });
});
