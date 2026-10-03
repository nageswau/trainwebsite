import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import { ALL_TYPES, type AppointmentRow } from "@/lib/bdmAppointments";

const router = vi.hoisted(() => ({ push: vi.fn() }));
const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/bdm/appointments", useSearchParams: () => new URLSearchParams(search.value) }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", bdm: { id: "b1", full_name: "Asha", active: true }, ...over,
});
const page = (items: AppointmentRow[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockClear();
  search.value = "";
});

describe("BdmAppointmentsPanel (bdm-006 §6.2, §12.2)", () => {
  it("asks for today onward by default and renders rows with IST times and text statuses", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([row(), row({ id: "a2", code: "APT-000002", status: "cancelled" })]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    expect(await screen.findByRole("link", { name: "APT-000001" })).toHaveAttribute("href", "/bdm/appointments/a1");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/date_from=\d{4}-\d{2}-\d{2}/);
    expect(screen.getAllByText(/07 Jan 2030, 10:00 IST/)).toHaveLength(2);
    expect(within(screen.getByRole("region", { name: "Appointments" })).getByText("Cancelled")).toHaveClass("status", "error");
    expect(screen.queryByRole("columnheader", { name: "BDM" })).toBeNull();
  });

  it("shows the BDM empty state with a booking link", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    expect(await screen.findByText("No appointments yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Book appointment" })[0]).toHaveAttribute("href", "/bdm/appointments/new");
  });

  it("shows the manager empty state, a BDM column and no booking link", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />);
    expect(await screen.findByText("Your team has no appointments in this period.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Book appointment" })).toBeNull();
  });

  it("shows no-match with clear filters, and retries after a failure", async () => {
    search.value = "status=cancelled";
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No appointments match these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(router.push).toHaveBeenCalledWith("/bdm/appointments", { scroll: false });
  });

  it("pushes filter changes into the URL", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([row()])))));
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "confirmed" } });
    expect(router.push).toHaveBeenLastCalledWith("/bdm/appointments?status=confirmed", { scroll: false });
  });

  it("shows an organization filter chip from the URL", async () => {
    search.value = "organization=o1";
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([row()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    expect(String(fetchMock.mock.calls[0][0])).toContain("organization_id=o1");
    expect(screen.getByText("Showing one organization")).toBeInTheDocument();
  });

  it("filters by BDM from the URL and maps the type filter to the API", async () => {
    search.value = "bdm=b9&type=college_meeting";
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([row()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("bdm_user_id=b9");
    expect(url).toContain("appointment_type=college_meeting");
    expect(screen.getByText("Showing one BDM")).toBeInTheDocument();
  });

  it("shows the past-the-end state when the page is empty but the total is not", async () => {
    search.value = "offset=100";
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => Promise.resolve(res(page([], 60, 100)))));
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    expect(await screen.findByText("This page is past the end of the list.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to the first page" }));
    expect(router.push).toHaveBeenCalledWith("/bdm/appointments", { scroll: false });
  });

  it("keeps the picked BDM's name in the select after the filter applies", async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => Promise.resolve(String(input).includes("/team") ? res({ items: [{ id: "b9", full_name: "Ravi Kumar", employee_id: "E9", bdm_type: "college" }], total: 1 }) : res(page([row()]))));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    fireEvent.focus(screen.getByRole("combobox", { name: "BDM" }));
    fireEvent.click(await screen.findByRole("option", { name: /Ravi Kumar/ }));
    expect(router.push).toHaveBeenLastCalledWith("/bdm/appointments?bdm=b9", { scroll: false });
    search.value = "bdm=b9";
    view.rerender(<BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("bdm_user_id=b9"))).toBe(true));
    expect((screen.getByRole("combobox", { name: "BDM" }) as HTMLInputElement).value).toContain("Ravi Kumar");
  });
});
