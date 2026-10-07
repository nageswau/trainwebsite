import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerLifecycle from "@/components/AdminTelecallerLifecycle";
import type { TelecallerAdminRow } from "@/lib/telecaller";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row: TelecallerAdminRow = {
  id: "t1", full_name: "Ravi", email: "ravi@x.local", phone: null, active: true, team: "it", employee_id: "T-1",
  reporting_manager: { id: "m1", full_name: "Meena", active: true }, manager_active: true,
};
const OPEN = { leads: 4, follow_ups: 2, appointments: 1 };
const NONE = { leads: 0, follow_ups: 0, appointments: 0 };
const telecallers = { items: [row, { ...row, id: "t2", full_name: "Asha", employee_id: "T-2", email: "asha@x.local" }], total: 2, limit: 20, offset: 0 };
const managers = { items: [{ id: "m2", full_name: "Kiran", email: "k@x.local", telecaller_count: 0 }], total: 1, limit: 20, offset: 0 };
const moved = { leads: 4, follow_ups: 2, appointments: 1 };

type Mock = ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
/** GET open-work -> `counts`; telecaller search -> Ravi + Asha; manager search -> Kiran; POST -> `post`. */
function route(counts: unknown = OPEN, post: Response = res({ id: "t1" })): Mock {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) => {
    const u = String(url);
    if (init?.method === "POST") return Promise.resolve(post.clone());
    if (u.endsWith("/open-work")) return Promise.resolve(counts instanceof Response ? counts.clone() : res(counts));
    if (u.includes("telecaller-managers")) return Promise.resolve(res(managers));
    return Promise.resolve(res(telecallers));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
const posts = (mock: Mock) => mock.mock.calls.filter(([, init]) => init?.method === "POST");
const postOf = (mock: Mock) => ({ url: String(posts(mock)[0][0]), body: JSON.parse(String(posts(mock)[0][1]?.body)) });

function mount(mode: "deactivate" | "handover" | "move" = "deactivate", overrides: Partial<TelecallerAdminRow> = {}) {
  const onDone = vi.fn();
  const onCancel = vi.fn();
  render(<AdminTelecallerLifecycle row={{ ...row, ...overrides }} mode={mode} onDone={onDone} onCancel={onCancel} />);
  return { onDone, onCancel };
}

async function pickAsha() {
  fireEvent.change(screen.getByRole("combobox", { name: "Hand the leads to" }), { target: { value: "as" } });
  fireEvent.click(await screen.findByRole("option", { name: /Asha/ }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminTelecallerLifecycle (tel-025)", () => {
  it("shows a loading state, then the open work", async () => {
    route();
    mount();
    expect(screen.getByRole("status")).toHaveTextContent("Loading open work…");
    expect(await screen.findByText("Open work: 4 open leads, with 2 open follow-ups and 1 appointment.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Deactivate Ravi" })).toBeInTheDocument();
  });

  it("a failed count load offers Retry", async () => {
    const mock = route(res({ detail: "boom" }, 500));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load Ravi's open work.");
    mock.mockImplementation(() => Promise.resolve(res(OPEN)));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Open work: 4 open leads/)).toBeInTheDocument();
  });

  it("needs a choice before it can confirm (AC3)", async () => {
    route();
    mount();
    const confirm = await screen.findByRole("button", { name: "Confirm deactivate" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Another IT telecaller" }));
    expect(confirm).toBeDisabled(); // a telecaller must be picked too
    await pickAsha();
    expect(confirm).toBeEnabled();
  });

  it("hands the leads to the picked telecaller, never offering the leaving one", async () => {
    const mock = route(OPEN, res({ id: "t1", active: false, target: "telecaller", moved, rules_removed: 0 }));
    const { onDone } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "Another IT telecaller" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Hand the leads to" }), { target: { value: "a" } });
    expect(await screen.findByRole("option", { name: /Asha/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Ravi/ })).not.toBeInTheDocument();
    const search = mock.mock.calls.map(([u]) => String(u)).find((u) => u.includes("/api/v1/admin/telecallers?"));
    expect(search).toContain("team=it");
    expect(search).toContain("active=true");
    fireEvent.click(screen.getByRole("option", { name: /Asha/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Ravi. 4 open leads now with Asha."));
    expect(postOf(mock)).toEqual({ url: "/api/v1/admin/telecallers/t1/deactivate", body: { target: "telecaller", reassign_to: "t2" } });
  });

  it("can send the leads to the team's unassigned queue", async () => {
    const mock = route(OPEN, res({ id: "t1", active: false, target: "queue", moved, rules_removed: 0 }));
    const { onDone } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "IT unassigned queue" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Ravi. 4 open leads moved to the IT unassigned queue."));
    expect(postOf(mock).body).toEqual({ target: "queue" });
  });

  it("with no open work there is nothing to choose", async () => {
    const mock = route(NONE, res({ id: "t1", active: false, target: null, moved: NONE, rules_removed: 0 }));
    const { onDone } = mount();
    expect(await screen.findByText("Ravi has no open leads.")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Ravi."));
    expect(postOf(mock).body).toEqual({});
  });

  it("keeps the server's 4xx sentence and words a 5xx plainly, focusing the error", async () => {
    route(OPEN, res({ detail: "Choose an active telecaller of the same team" }, 422));
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: "IT unassigned queue" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    const alert = await screen.findByText("Choose an active telecaller of the same team");
    await waitFor(() => expect(alert).toHaveFocus());
    cleanup();
    route(OPEN, res({ detail: "boom" }, 500));
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: "IT unassigned queue" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("We couldn't deactivate Ravi. Please try again.")).toBeInTheDocument();
  });

  it("Escape cancels", async () => {
    route();
    const { onCancel } = mount();
    fireEvent.keyDown(await screen.findByRole("group", { name: "Deactivate Ravi" }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });

  it("hands over an inactive telecaller's leads (LC4)", async () => {
    const mock = route(OPEN, res({ id: "t1", target: "queue", moved }));
    const { onDone } = mount("handover", { active: false });
    expect(await screen.findByRole("group", { name: "Reassign Ravi's open leads" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "IT unassigned queue" }));
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("4 open leads from Ravi moved to the IT unassigned queue."));
    expect(postOf(mock).url).toBe("/api/v1/admin/telecallers/t1/handover");
  });

  it("moves to the other team, keeping the leads on the old team, with an optional new manager (T22)", async () => {
    const mock = route(OPEN, res({ id: "t1", team: "overseas", target: "telecaller", moved, rules_removed: 1 }));
    const { onDone } = mount("move");
    expect(await screen.findByText(/Move Ravi from the IT team to the Overseas team/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Another IT telecaller" }));
    await pickAsha();
    fireEvent.change(screen.getByRole("combobox", { name: "Reporting manager" }), { target: { value: "ki" } });
    fireEvent.click(await screen.findByRole("option", { name: /Kiran/ }));
    fireEvent.click(screen.getByRole("button", { name: "Move team" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Moved Ravi to the Overseas team; they sign in again there. 4 open leads now with Asha."));
    expect(postOf(mock)).toEqual({
      url: "/api/v1/admin/telecallers/t1/move-team",
      body: { team: "overseas", target: "telecaller", reassign_to: "t2", reporting_manager_user_id: "m2" },
    });
  });
});
