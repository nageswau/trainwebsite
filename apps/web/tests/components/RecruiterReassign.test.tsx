import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterReassign from "@/components/RecruiterReassign";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }) }));

const row = { id: "r1", full_name: "Kiran", email: "kiran@x.local", phone: null, active: true, employee_id: "R-1", work: { companies: 12, requirements: 3, follow_ups: 1 } };
const team = {
  items: [
    { id: "r1", full_name: "Kiran", email: "kiran@x.local", active: true },
    { id: "r2", full_name: "Meera", email: "m@x.local", active: true },
    { id: "r3", full_name: "Old", email: "o@x.local", active: false },
  ],
  total: 3,
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

let reassign: (body: unknown) => Promise<Response>;
const fetchMock = vi.fn((url: string, init?: RequestInit) => {
  if (url.includes("/manager/team")) return json(200, team);
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
  fireEvent.click(screen.getByRole("button", { name: "Reassign Kiran's work" }));
  expect(screen.getByRole("group", { name: "Reassign Kiran's work" })).toHaveTextContent("Kiran has 12 companies, 3 requirements and 1 open follow-up.");
  const combo = screen.getByRole("combobox", { name: /Move everything to/ });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "e" } });
  fireEvent.click(await screen.findByRole("option", { name: "Meera — m@x.local" }));
}

describe("RecruiterReassign (rec-037)", () => {
  it("shows no button when the recruiter has no work", () => {
    render(<RecruiterReassign row={{ ...row, work: { companies: 0, requirements: 0, follow_ups: 0 } }} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers only other active team-mates, posts both ids and announces what moved", async () => {
    reassign = (body) => {
      expect(body).toEqual({ from_user_id: "r1", to_user_id: "r2" });
      return json(200, { from_user_id: "r1", to_user_id: "r2", moved: { companies: 12, requirements: 3, follow_ups: 1 } });
    };
    render(<RecruiterReassign row={row} />);
    await openAndPick();
    expect(screen.queryByRole("option", { name: /Kiran|Old/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Moved to Meera: 12 companies, 3 requirements and 1 open follow-up.");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("keeps the server's sentence for a 4xx and plain words for a 5xx, focused", async () => {
    reassign = () => json(422, { detail: "Choose an active recruiter from your team" });
    render(<RecruiterReassign row={row} />);
    await openAndPick();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Choose an active recruiter from your team");
    await waitFor(() => expect(alert).toHaveFocus());
    reassign = () => json(500, { detail: "boom" });
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("We couldn't reassign Kiran's work. Please try again."));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("disables Reassign until a recruiter is picked; Escape cancels and returns focus", async () => {
    render(<RecruiterReassign row={row} />);
    fireEvent.click(screen.getByRole("button", { name: "Reassign Kiran's work" }));
    expect(screen.getByRole("button", { name: "Reassign" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("group"), { key: "Escape" });
    expect(screen.queryByRole("group")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Reassign Kiran's work" })).toHaveFocus());
  });
});
