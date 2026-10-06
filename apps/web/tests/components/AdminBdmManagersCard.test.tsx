import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmManagersCard from "@/components/AdminBdmManagersCard";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pg = (items: unknown[], total = items.length) => ({ items, total, limit: 50, offset: 0 });
const MEERA = { id: "m1", full_name: "Meera", email: "meera@x.local", bdm_count: 2 };
const RAVI = { id: "m2", full_name: "Ravi", email: "ravi@x.local", bdm_count: 0 };

type Mock = ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
function route(list: () => Response = () => res(pg([MEERA, RAVI])), post: Response = res({ id: "m1", active: false, moved_bdms: 2 })): Mock {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((_url, init) =>
    Promise.resolve(init?.method === "POST" ? post.clone() : list()));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const posts = (mock: Mock) => mock.mock.calls.filter(([, init]) => init?.method === "POST");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminBdmManagersCard (bdm-025 AC4)", () => {
  it("lists active managers with how many BDMs report to them", async () => {
    route();
    render(<AdminBdmManagersCard onChanged={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading BDM managers…");
    const table = await screen.findByRole("region", { name: "BDM managers" });
    expect(within(table).getByText("Meera")).toBeInTheDocument();
    expect(within(table).getByText("2 BDMs")).toBeInTheDocument();
    expect(within(table).getByText("0 BDMs")).toBeInTheDocument();
  });

  it("an empty list and a failed load read differently", async () => {
    const mock = route(() => res(pg([])));
    render(<AdminBdmManagersCard onChanged={vi.fn()} />);
    expect(await screen.findByText("No active BDM managers.")).toBeInTheDocument();
    cleanup();
    mock.mockImplementation(() => Promise.resolve(res({ detail: "x" }, 500)));
    render(<AdminBdmManagersCard onChanged={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the BDM managers list.");
    mock.mockImplementation(() => Promise.resolve(res(pg([MEERA]))));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Meera")).toBeInTheDocument();
  });

  it("a manager with BDMs needs a replacement manager, never themself", async () => {
    const mock = route();
    const onChanged = vi.fn();
    render(<AdminBdmManagersCard onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Meera" }));
    const group = screen.getByRole("group", { name: "Deactivate Meera" });
    expect(within(group).getByText("Move their 2 BDMs to another manager first. Pending travel approvals move with them.")).toBeInTheDocument();
    const confirm = within(group).getByRole("button", { name: "Confirm deactivate" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(group).getByRole("combobox", { name: "Replacement manager" }), { target: { value: "e" } });
    await within(group).findByRole("option", { name: /Ravi/ });
    expect(within(group).queryByRole("option", { name: /Meera/ })).toBeNull();
    fireEvent.click(within(group).getByRole("option", { name: /Ravi/ }));
    fireEvent.click(confirm);
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Meera. 2 BDMs now report to Ravi."));
    expect(posts(mock)[0][0]).toBe("/api/v1/admin/bdm-managers/m1/deactivate");
    expect(JSON.parse(String(posts(mock)[0][1]?.body))).toEqual({ reassign_to: "m2" });
  });

  it("a manager with no BDMs is deactivated without a replacement", async () => {
    const mock = route(undefined, res({ id: "m2", active: false, moved_bdms: 0 }));
    const onChanged = vi.fn();
    render(<AdminBdmManagersCard onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Ravi" }));
    const group = screen.getByRole("group", { name: "Deactivate Ravi" });
    expect(within(group).queryByRole("combobox")).toBeNull();
    fireEvent.click(within(group).getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Ravi."));
    expect(JSON.parse(String(posts(mock)[0][1]?.body))).toEqual({});
  });

  it("shows a refusal in an alert with focus; Keep active and Escape close the group", async () => {
    route(undefined, res({ detail: "Choose another active BDM manager" }, 422));
    render(<AdminBdmManagersCard onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    const alert = await screen.findByText("Choose another active BDM manager");
    await waitFor(() => expect(alert).toHaveFocus());
    fireEvent.keyDown(alert, { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate Ravi" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep active" }));
    expect(screen.queryByRole("group", { name: "Deactivate Ravi" })).toBeNull();
  });
});
