import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminLeadManagementPanel from "@/components/AdminLeadManagementPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type Row = Record<string, unknown>;
const row = (id: string, over: Row = {}): Row => ({
  id, name: `Lead ${id}`, email: `${id}@example.com`, phone: null, division: "it", subject: "Python", status: "new", source: "website",
  crm_sync_status: "sent", organization: null, bdm: null, converted_user: null, ...over,
});
const stMary = { id: "o1", code: "ORG-000001", name: "St Mary" };
const rows = [
  row("w1"),
  row("b1", { source: "bdm", organization: stMary, bdm: { id: "u1", full_name: "Asha" } }),
  row("b2", { source: "bdm", organization: { id: "o2", code: "ORG-000002", name: "Govt College" }, bdm: { id: "u1", full_name: "Asha" } }),
];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method ? Promise.resolve(res({}, 500)) : Promise.resolve(res(rows))));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const tableRow = async (name: string) => (await screen.findByRole("rowheader", { name })).closest("tr") as HTMLElement;

describe("AdminLeadManagementPanel (ADM-002 + bdm-017 spec §6)", () => {
  it("shows the organization of each lead, Website for unattributed ones", async () => {
    render(<AdminLeadManagementPanel />);
    expect(within(await tableRow("Lead w1")).getByText("Website")).toBeInTheDocument();
    expect(within(await tableRow("Lead b1")).getByText("ORG-000001 · St Mary")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Organization" })).toBeInTheDocument();
  });

  it("filters by organization", async () => {
    render(<AdminLeadManagementPanel />);
    await tableRow("Lead b1");
    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "o1" } });
    expect(screen.queryByRole("rowheader", { name: "Lead w1" })).toBeNull();
    expect(screen.queryByRole("rowheader", { name: "Lead b2" })).toBeNull();
    expect(screen.getByRole("rowheader", { name: "Lead b1" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "website" } });
    expect(screen.getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["Lead w1"]);
  });

  it("links a student by email and shows who the lead converted to", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead b1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ ...rows[1], status: "converted", converted_user: { id: "s1", full_name: "Stu Dent", email: "stu@example.com" } })));
    fireEvent.click(within(tr).getByRole("button", { name: "Link student to Lead b1" }));
    fireEvent.change(within(tr).getByLabelText("Student account email for Lead b1"), { target: { value: "stu@example.com" } });
    fireEvent.click(within(tr).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(within(tr).getByText("Stu Dent (stu@example.com)")).toBeInTheDocument());
    expect(within(tr).getByRole("status")).toHaveTextContent("Student linked.");
    const [url, init] = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/admin/leads/b1/conversion");
    expect([init.method, JSON.parse(String(init.body))]).toEqual(["POST", { student_email: "stu@example.com" }]);
  });

  it("a refused link keeps the email and shows the server's words in the row", async () => {
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead b1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "Enter the email of an active student account in this lead's division" }, 422)));
    fireEvent.click(within(tr).getByRole("button", { name: "Link student to Lead b1" }));
    fireEvent.change(within(tr).getByLabelText("Student account email for Lead b1"), { target: { value: "x@example.com" } });
    fireEvent.click(within(tr).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(within(tr).getByRole("status")).toHaveTextContent("Enter the email of an active student account"));
    expect(within(tr).getByLabelText("Student account email for Lead b1")).toHaveValue("x@example.com");
  });

  it("unlinks after a confirm", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res([row("c1", { converted_user: { id: "s1", full_name: "Stu Dent", email: "stu@example.com" }, status: "converted" })])));
    render(<AdminLeadManagementPanel />);
    const tr = await tableRow("Lead c1");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res(row("c1", { status: "converted" }))));
    fireEvent.click(within(tr).getByRole("button", { name: "Unlink student from Lead c1" }));
    fireEvent.click(within(tr).getByRole("button", { name: "Yes, unlink" }));
    await waitFor(() => expect(within(tr).getByRole("button", { name: "Link student to Lead c1" })).toBeInTheDocument());
    expect((fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit])[1].method).toBe("DELETE");
  });
});
