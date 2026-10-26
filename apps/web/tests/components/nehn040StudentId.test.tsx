import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminUserManagementPanel from "@/components/AdminUserManagementPanel";
import AgentNetworkRecords from "@/components/AgentNetworkRecords";
import AgentStudentDetailPanel from "@/components/AgentStudentDetailPanel";
import AgentStudentsPanel from "@/components/AgentStudentsPanel";

// nehn-040 (DEC-SCOPE-279): the Student ID is shown in list rows and the agency detail header, and the admin search matches it.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin users (AC1, AC3)", () => {
  const base = { division: "overseas", phone: null, profile: {}, active: true, provisioning_status: "active" };
  const users = [
    { ...base, id: "s", name: "Sana Student", email: "sana@example.local", role: "overseas_student", student_code: "3FA9C21B" },
    { ...base, id: "c", name: "Cara Counselor", email: "cara@example.local", role: "counselor", student_code: null },
  ];

  it("shows the Student ID on the student's row and finds the student by it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(users))));
    render(<AdminUserManagementPanel />);
    const row = (await screen.findByText("Sana Student")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Student ID 3FA9C21B")).toBeInTheDocument();
    expect(within(screen.getByText("Cara Counselor").closest("tr") as HTMLElement).queryByText(/Student ID/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Search by name, email, role, or Student ID"), { target: { value: "3fa9c21b" } });
    expect(screen.getByText("Sana Student")).toBeInTheDocument();
    expect(screen.queryByText("Cara Counselor")).toBeNull();
  });
});

describe("Agency students (AC3)", () => {
  const item = {
    id: "s1", has_login: false, full_name: "Asha Rao", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active",
    assigned_to: null, created_at: "2026-10-01T09:00:00Z", student_code: "0A1B2C3D",
  } as const;

  it("shows the Student ID on each card and names it in the search", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [item], total: 1, limit: 20, offset: 0 }))));
    render(<AgentStudentsPanel memberRole="master" />);
    const card = (await screen.findByText("Asha Rao")).closest("li") as HTMLElement;
    expect(within(card).getByText("Student ID 0A1B2C3D")).toBeInTheDocument();
    expect(screen.getByLabelText("Search students")).toHaveAttribute("placeholder", "Name, email, phone or Student ID");
  });

  it("shows the Student ID in the detail header", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [], total: 0, limit: 20, offset: 0 }))));
    const detail = {
      ...item, date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null, preferred_course: null, notes: null,
      created_by: "Master", archived_at: null, archived_by: null, updated_at: "2026-10-01T09:00:00Z", counseling: null,
    };
    render(<AgentStudentDetailPanel detail={detail} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText("Student ID 0A1B2C3D")).toBeInTheDocument();
  });
});

describe("Admin users server search (QA-01)", () => {
  it("asks the server for matches, so a student beyond the capped list is found", async () => {
    const old = { division: "overseas", phone: null, profile: {}, active: true, provisioning_status: "active", id: "o", name: "Olga Older", email: "olga@example.local", role: "overseas_student", student_code: "9F00AA11" };
    const fetchMock = vi.fn((url: string) => Promise.resolve(res(new URL(url, "http://x").searchParams.get("q") === "9f00aa11" ? [old] : [])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminUserManagementPanel />);
    await screen.findByText("No users found.");
    fireEvent.change(screen.getByLabelText("Search by name, email, role, or Student ID"), { target: { value: "9f00aa11" } });
    expect(await screen.findByText("Olga Older")).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/api/v1/admin/users?q=9f00aa11");
  });
});

describe("Agent network students (AC3)", () => {
  it("lists the Student ID column", async () => {
    const student = { id: "n1", full_name: "Student n1", student_code: "ABCDEF12", status: "active", assigned_code: null, has_login: false, applications: 0, created_at: "2026-09-30T00:00:00Z" };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ items: [student], total: 1, limit: 20, offset: 0 }))));
    render(<AgentNetworkRecords orgId="3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f" kind="students" />);
    const row = (await screen.findByText("Student n1")).closest("tr") as HTMLElement;
    expect(screen.getByRole("columnheader", { name: "Student ID" })).toBeInTheDocument();
    expect(within(row).getByText("ABCDEF12")).toHaveAttribute("data-label", "Student ID");
  });
});
