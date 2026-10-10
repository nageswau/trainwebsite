import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PartnershipReassign from "@/components/PartnershipReassign";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }) }));

const row = { id: "p1", full_name: "Rahul", email: "rahul@x.local", phone: null, active: true, employee_id: "P-1", work: { primary: 3, backup: 1, tasks: 2 } };
const options = { items: [{ id: "p1", full_name: "Rahul", email: "rahul@x.local" }, { id: "p2", full_name: "Meera", email: "m@x.local" }], total: 2 };

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

let reassign: (body: unknown) => Promise<Response>;
const fetchMock = vi.fn((url: string, init?: RequestInit) => {
  if (url.includes("manager-options")) return json(200, options);
  return reassign(JSON.parse(String(init?.body)));
});

beforeEach(() => {
  fetchMock.mockClear();
  refresh.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openAndPick() {
  fireEvent.click(screen.getByRole("button", { name: "Reassign Rahul's work" }));
  expect(screen.getByRole("group", { name: "Reassign Rahul's work" })).toHaveTextContent("Rahul is primary on 3 universities, backup on 1, 2 open tasks.");
  const combo = screen.getByRole("combobox", { name: /Move everything to/ });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "m" } });
  fireEvent.click(await screen.findByRole("option", { name: "Meera — m@x.local" }));
}

describe("PartnershipReassign (upc-032)", () => {
  it("shows no button when the manager has no work", () => {
    render(<PartnershipReassign row={{ ...row, work: { primary: 0, backup: 0, tasks: 0 } }} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("never offers the manager themselves, posts both ids and announces what moved", async () => {
    reassign = (body) => {
      expect(body).toEqual({ from_user_id: "p1", to_user_id: "p2" });
      return json(200, { from_user_id: "p1", to_user_id: "p2", moved: { primary: 3, backup: 1, tasks: 2 } });
    };
    render(<PartnershipReassign row={row} />);
    await openAndPick();
    expect(screen.queryByRole("option", { name: /Rahul/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Moved to Meera: primary on 3 universities, backup on 1, 2 open tasks.");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("keeps the server's sentence for a 4xx and plain words for a 5xx, focused", async () => {
    reassign = () => json(422, { detail: "Choose an active partnership manager from your team" });
    render(<PartnershipReassign row={row} />);
    await openAndPick();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Choose an active partnership manager from your team");
    await waitFor(() => expect(alert).toHaveFocus());
    reassign = () => json(500, { detail: "boom" });
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("We couldn't reassign Rahul's work. Please try again."));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("disables Reassign until a manager is picked; Escape cancels and returns focus", async () => {
    render(<PartnershipReassign row={row} />);
    fireEvent.click(screen.getByRole("button", { name: "Reassign Rahul's work" }));
    expect(screen.getByRole("button", { name: "Reassign" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("group"), { key: "Escape" });
    expect(screen.queryByRole("group")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Reassign Rahul's work" })).toHaveFocus());
  });
});
