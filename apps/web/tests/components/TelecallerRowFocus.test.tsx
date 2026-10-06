import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerCampaignRow from "@/components/TelecallerCampaignRow";
import TelecallerProductRow from "@/components/TelecallerProductRow";

// QA follow-up: after Deactivate / Reactivate the list reloads; focus must land on the row's new status button, not on Edit.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const product = { id: "p1", group: "it" as const, name: "SAP", team: "it" as const, program: null, active: true, sort_order: 2 };
const campaign = {
  id: "c1", name: "Sep push", source: "instagram", product: { id: "p1", name: "SAP", group: "it" as const, active: true },
  start_date: "2026-09-01", end_date: null, active: true,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const table = (row: React.ReactNode) => <table><tbody>{row}</tbody></table>;

describe("status buttons keep focus across the reload", () => {
  it("product: Deactivate → Reactivate, and back", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}))));
    const onChanged = vi.fn();
    const { rerender } = render(table(<TelecallerProductRow row={product} programs={[]} onChanged={onChanged} />));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate SAP" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated SAP."));
    rerender(table(<TelecallerProductRow row={{ ...product, active: false }} programs={[]} onChanged={onChanged} />));
    await waitFor(() => expect(screen.getByRole("button", { name: "Reactivate SAP" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Reactivate SAP" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Reactivated SAP."));
    rerender(table(<TelecallerProductRow row={product} programs={[]} onChanged={onChanged} />));
    await waitFor(() => expect(screen.getByRole("button", { name: "Deactivate SAP" })).toHaveFocus());
  });

  it("campaign: Deactivate → Reactivate", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}))));
    const onChanged = vi.fn();
    const { rerender } = render(table(<TelecallerCampaignRow row={campaign} products={[]} onChanged={onChanged} />));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Sep push" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Sep push."));
    rerender(table(<TelecallerCampaignRow row={{ ...campaign, active: false }} products={[]} onChanged={onChanged} />));
    await waitFor(() => expect(screen.getByRole("button", { name: "Reactivate Sep push" })).toHaveFocus());
  });

  it("keeps focus on the row (Edit) while the reload has not arrived", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}))));
    const onChanged = vi.fn();
    render(table(<TelecallerProductRow row={product} programs={[]} onChanged={onChanged} />));
    fireEvent.click(screen.getByRole("button", { name: "Deactivate SAP" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit SAP" })).toHaveFocus());
  });
});
