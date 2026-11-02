import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerStrategyPanel from "@/components/TelecallerStrategyPanel";

// itc-006 (DEC-SCOPE-337 D3/D6): each team's fallback when no rule matches -- round robin or the fewest open leads.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const it_ = { team: "it", team_label: "IT", strategy: "round_robin", editable: true };
const os = { team: "overseas", team_label: "Overseas", strategy: "workload", editable: false };

type Call = { url: string; init?: RequestInit };
function serve(onGet: () => Response, onPut?: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(init?.method === "PUT" ? (onPut ? onPut(call) : res({})) : onGet());
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TelecallerStrategyPanel", () => {
  it("shows each team's strategy; a team the manager cannot change is read-only", async () => {
    serve(() => res({ items: [it_, os] }));
    render(<TelecallerStrategyPanel />);
    expect(screen.getByRole("status").textContent).toMatch(/Loading/);
    const itCard = await screen.findByRole("region", { name: "IT team" });
    expect((within(itCard).getByLabelText("When no rule matches") as HTMLSelectElement).value).toBe("round_robin");
    const osCard = screen.getByRole("region", { name: "Overseas team" });
    const osSelect = within(osCard).getByLabelText("When no rule matches") as HTMLSelectElement;
    expect(osSelect.value).toBe("workload");
    expect(osSelect.disabled).toBe(true);
    expect(within(osCard).queryByRole("button")).toBeNull();
    expect(within(osCard).getByText(/Only a manager with telecallers on the Overseas team/)).toBeTruthy();
  });

  it("saves a new strategy and says what changes", async () => {
    const calls = serve(() => res({ items: [it_] }), () => res({ ...it_, strategy: "workload" }));
    render(<TelecallerStrategyPanel />);
    const card = await screen.findByRole("region", { name: "IT team" });
    const save = within(card).getByRole("button", { name: "Save IT strategy" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // nothing changed yet
    fireEvent.change(within(card).getByLabelText("When no rule matches"), { target: { value: "workload" } });
    fireEvent.click(save);
    fireEvent.click(save); // a double click sends one request
    expect(await within(card).findByText(/Saved\. New IT leads that no rule matches go to the telecaller with the fewest open leads\./)).toBeTruthy();
    const puts = calls.filter((c) => c.init?.method === "PUT");
    expect(puts).toHaveLength(1);
    expect(puts[0].url).toBe("/api/v1/telecaller/distribution-strategy/it");
    expect(JSON.parse(String(puts[0].init!.body))).toEqual({ strategy: "workload" });
  });

  it("shows the server's refusal inline", async () => {
    serve(() => res({ items: [it_] }), () => res({ detail: "You can only change the strategy of a team your telecallers are on" }, 403));
    render(<TelecallerStrategyPanel />);
    const card = await screen.findByRole("region", { name: "IT team" });
    fireEvent.change(within(card).getByLabelText("When no rule matches"), { target: { value: "workload" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save IT strategy" }));
    expect(await within(card).findByText("You can only change the strategy of a team your telecallers are on")).toBeTruthy();
  });

  it("offers a retry when loading fails", async () => {
    let fail = true;
    serve(() => (fail ? res({ detail: "x" }, 500) : res({ items: [it_] })));
    render(<TelecallerStrategyPanel />);
    expect(await screen.findByText("Unable to load the team strategies.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry loading strategies" }));
    expect(await screen.findByRole("region", { name: "IT team" })).toBeTruthy();
  });
});
