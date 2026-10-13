import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TelecallingPage from "@/app/management/telecalling/page";
import ManagementTelecalling from "@/components/ManagementTelecalling";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { Telecalling, TelecallingFigures } from "@/lib/managementTelecalling";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { redirect } from "next/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/telecalling" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const figures = (over: Partial<TelecallingFigures> = {}): TelecallingFigures => ({
  leads: 0, calls: 0, connected: 0, interested: 0, follow_ups: 0, appointments: 0, converted: 0, lost: 0, counselling: 0, conversion: null, ...over,
}); // prettier-ignore
const ravi = figures({ leads: 40, calls: 1200, connected: 800, interested: 90, follow_ups: 60, appointments: 30, converted: 10, lost: 25, counselling: 20, conversion: 25 });
const data: Telecalling = {
  date_from: "2026-10-01",
  date_to: "2026-10-13",
  totals: ravi,
  teams: [
    { team: "it", label: "IT", telecallers: 2, ...ravi },
    { team: "overseas", label: "Overseas", telecallers: 0, ...figures() },
  ],
  telecallers: [
    { user_id: "t1", full_name: "Ravi Telecaller", team: "IT", active: true, ...ravi },
    { user_id: "t2", full_name: "Old Caller", team: "IT", active: false, ...figures() },
  ],
  chain: [
    { key: "calls", label: "Calls", value: 1200, share: null },
    { key: "interested", label: "Interested", value: 90, share: 7.5 },
    { key: "counselling", label: "Counseling", value: 20, share: 1.7 },
    { key: "registration", label: "Registration", value: 10, share: 0.8 },
  ],
};
const EMPTY = { date_from: "", date_to: "" };

function answer(me: ManagementMe | Error, body: Telecalling | Error = data) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const result = path === "/api/v1/management/me" ? me : String(path).startsWith("/api/v1/management/telecalling") ? body : ({ id: "x", role: "partner" } as never);
    if (result instanceof Error) throw result;
    return result as never;
  });
}

const page = (search: Record<string, string> = {}) => TelecallingPage({ searchParams: Promise.resolve(search) });

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("mgmt-019 telecalling page", () => {
  it("reads the dashboard for the address's period and shows it in the management shell", async () => {
    answer(partner);
    const tree = elements(await page({ date_from: "2026-10-01", date_to: "2026-10-13" }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/telecalling?date_from=2026-10-01&date_to=2026-10-13");
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Leads & calls", href: "/management/telecalling" });
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Telecalling" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Command Center" }).getAttribute("href")).toBe("/management");
  });

  it("drops a submitted form's empty dates from the address by one redirect", async () => {
    answer(partner);
    await page({ date_from: "", date_to: "2026-10-13" });
    expect(redirect).toHaveBeenCalledWith("/management/telecalling?date_to=2026-10-13");
    vi.mocked(redirect).mockClear();
    await page({ date_to: "2026-10-13" });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin);
    const shell = elements(await page()).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the access card when the dashboard is refused (the accountant's 403)", async () => {
    answer({ ...partner, role: "accountant", tiers: { operational: false, finance: true, partner_only: false } }, new ApiError("Operational access required", 403));
    render(await page());
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Operational access required")).toBeTruthy();
  });

  it("shows the API's own words for a 422 and a generic message for anything else", async () => {
    answer(partner, new ApiError("The range can't end in the future", 422));
    let shell = elements(await page({ date_to: "2099-01-01" })).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The range can't end in the future");
    cleanup();
    answer(partner, new ApiError("boom", 500));
    shell = elements(await page()).find((el) => el.type === PortalShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The telecalling dashboard is unavailable right now. Please try again.");
  });
});

describe("mgmt-019 ManagementTelecalling", () => {
  it("shows the eight §14 figures in source order and telecaller conversion", () => {
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    const tiles = within(screen.getByRole("list", { name: "Company telecalling figures" })).getAllByRole("listitem");
    expect(tiles.map((tile) => tile.querySelector("span")?.textContent)).toEqual([
      "Leads assigned", "Calls attempted", "Connected", "Interested", "Follow-up", "Appointment", "Converted", "Lost", "Telecaller conversion",
    ]); // prettier-ignore
    expect(within(tiles[1]).getByText("1,200")).toBeTruthy();
    expect(within(tiles[8]).getByText("25%")).toBeTruthy();
    expect(screen.getByText(/01 Oct 2026 to 13 Oct 2026/)).toBeTruthy();
  });

  it("QA19-03: shows the chain with each later step's share of calls", () => {
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    const steps = within(screen.getByRole("list", { name: "Calls to registration" })).getAllByRole("listitem");
    expect(steps.map((step) => step.querySelector(".funnel-label")?.textContent)).toEqual(["Calls", "Interested", "Counseling", "Registration"]);
    expect(within(steps[1]).getByText("7.5% of calls")).toBeTruthy();
    expect(within(steps[3]).getByText("0.8% of calls")).toBeTruthy();
    expect(steps[0].querySelector(".funnel-percent")).toBeNull();
    expect(screen.getByText(/Each step shows its share of the calls/)).toBeTruthy();
  });

  it("QA19-04: spaces the tables from the chain card", () => {
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    expect(screen.getByRole("heading", { name: "By team" }).className).toBe("telecalling-section-title");
    expect(screen.getByRole("heading", { name: "By telecaller" }).className).toBe("telecalling-section-title");
  });

  it("lists both teams and every telecaller with conversion, inactive ones marked, under the #telecallers anchor", () => {
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    const teams = within(screen.getByRole("table", { name: "Telecalling by team" })).getAllByRole("row");
    expect(teams.map((row) => row.querySelector("th")?.textContent)).toEqual(["Team", "IT", "Overseas", "Company"]);
    expect(within(teams[2]).getByText("—")).toBeTruthy(); // no leads → no conversion
    const section = document.getElementById("telecallers")!;
    const rows = within(within(section).getByRole("table", { name: "Telecalling by telecaller" })).getAllByRole("row");
    expect(rows[1].textContent).toContain("Ravi Telecaller");
    expect(rows[2].querySelector("th")?.textContent).toBe("Old Caller (inactive)");
  });

  it("says so when there are no telecallers", () => {
    render(<ManagementTelecalling data={{ ...data, telecallers: [] }} error="" filters={EMPTY} />);
    expect(screen.getByRole("status").textContent).toBe("There are no telecallers yet.");
    expect(screen.queryByRole("table", { name: "Telecalling by telecaller" })).toBeNull();
  });

  it("offers the period as a GET form with the applied dates, and a link back to this month when one is set", () => {
    render(<ManagementTelecalling data={data} error="" filters={{ date_from: "2026-10-01", date_to: "" }} />);
    const form = screen.getByRole("form", { name: "Telecalling period" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe("/management/telecalling");
    expect((within(form).getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-01");
    expect(screen.getByRole("link", { name: "This month" }).getAttribute("href")).toBe("/management/telecalling");
    cleanup();
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    expect(screen.queryByRole("link", { name: "This month" })).toBeNull();
  });

  it("QA19-01: with no dates in the address the inputs show the period on screen (this month to date)", () => {
    render(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    const form = screen.getByRole("form", { name: "Telecalling period" });
    expect((within(form).getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-01");
    expect((within(form).getByLabelText("To") as HTMLInputElement).value).toBe("2026-10-13");
  });

  it("QA19-02: a client navigation to another period (This month, Back) resets the inputs", () => {
    const { rerender } = render(<ManagementTelecalling data={{ ...data, date_from: "2026-10-05" }} error="" filters={{ date_from: "2026-10-05", date_to: "" }} />);
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-05");
    rerender(<ManagementTelecalling data={data} error="" filters={EMPTY} />);
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-01");
  });

  it("shows the error and the form only when the dashboard could not be read", () => {
    render(<ManagementTelecalling data={null} error="The telecalling dashboard is unavailable right now. Please try again." filters={EMPTY} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Company telecalling figures" })).toBeNull();
    expect(screen.getByRole("form", { name: "Telecalling period" })).toBeTruthy();
  });
});
