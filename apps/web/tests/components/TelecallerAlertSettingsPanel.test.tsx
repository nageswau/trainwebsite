import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerAlertSettingsPanel from "@/components/TelecallerAlertSettingsPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

// tel-020 (DEC-SCOPE-111 AL1, AL11; API §12AE): the manager's alert thresholds, one card per team.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (team: string, label: string, over: Record<string, unknown> = {}) => ({
  team, team_label: label, not_contacted_hours: 24, hot_pending_hours: 4, updated_at: "2026-10-07T05:00:00Z", updated_by: null, ...over,
});
const settings = { items: [row("it", "IT"), row("overseas", "Overseas")] };

type Call = { url: string; init?: RequestInit };
function serve(put: (body: Record<string, unknown>) => Response | Promise<Response> = (b) => res(row("it", "IT", { ...b, updated_by: { id: "m1", full_name: "Mona Manager" } })), get: () => Promise<Response> = () => Promise.resolve(res(settings))) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return init?.method === "PUT" ? Promise.resolve(put(JSON.parse(String(init.body)))) : get();
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TelecallerAlertSettingsPanel", () => {
  it("shows a loading state, then both teams' thresholds", async () => {
    serve();
    render(<TelecallerAlertSettingsPanel />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading alert settings…");
    const it = await screen.findByRole("region", { name: "IT team" });
    expect(within(it).getByLabelText("Lead not contacted after (hours)")).toHaveValue(24);
    expect(within(it).getByLabelText("Hot lead pending after (hours)")).toHaveValue(4);
    expect(within(it).getByText("Default thresholds (never changed).")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Overseas team" })).toBeInTheDocument();
  });

  it("saves one team with whole numbers and shows who changed it", async () => {
    const calls = serve();
    render(<TelecallerAlertSettingsPanel />);
    const it = await screen.findByRole("region", { name: "IT team" });
    fireEvent.change(within(it).getByLabelText("Lead not contacted after (hours)"), { target: { value: "12" } });
    fireEvent.change(within(it).getByLabelText("Hot lead pending after (hours)"), { target: { value: "2" } });
    fireEvent.click(within(it).getByRole("button", { name: "Save IT thresholds" }));
    expect(await within(it).findByText("Saved. Alerts use the new thresholds from the next check (within 15 minutes).")).toBeInTheDocument();
    const put = calls.find((c) => c.init?.method === "PUT")!;
    expect(put.url).toBe("/api/v1/telecaller/settings/it");
    expect(JSON.parse(String(put.init!.body))).toEqual({ not_contacted_hours: 12, hot_pending_hours: 2 });
    expect(within(it).getByText(/Last changed by Mona Manager/)).toBeInTheDocument();
  });

  it("shows the API's sentence on a refused save and keeps the entry", async () => {
    serve(() => res({ detail: "Telecaller manager role required" }, 403));
    render(<TelecallerAlertSettingsPanel />);
    const it = await screen.findByRole("region", { name: "IT team" });
    fireEvent.change(within(it).getByLabelText("Lead not contacted after (hours)"), { target: { value: "36" } });
    fireEvent.click(within(it).getByRole("button", { name: "Save IT thresholds" }));
    expect(await within(it).findByText("Telecaller manager role required")).toBeInTheDocument();
    expect(within(it).getByLabelText("Lead not contacted after (hours)")).toHaveValue(36);
  });

  it("an out-of-range or blank entry is stopped by the form and sends nothing", async () => {
    const calls = serve();
    render(<TelecallerAlertSettingsPanel />);
    const it = await screen.findByRole("region", { name: "IT team" });
    const input = within(it).getByLabelText("Lead not contacted after (hours)");
    for (const value of ["0", "169", ""]) {
      fireEvent.change(input, { target: { value } });
      fireEvent.click(within(it).getByRole("button", { name: "Save IT thresholds" }));
      expect(input).toBeInvalid();
    }
    expect(calls.filter((c) => c.init?.method === "PUT")).toHaveLength(0);
  });

  it("a dropped connection keeps the entry and says so", async () => {
    serve(() => Promise.reject(new TypeError("offline")));
    render(<TelecallerAlertSettingsPanel />);
    const it = await screen.findByRole("region", { name: "IT team" });
    fireEvent.click(within(it).getByRole("button", { name: "Save IT thresholds" }));
    expect(await within(it).findByText(NOT_COMPLETED)).toBeInTheDocument();
  });

  it("disables the button while saving so a double click sends one request", async () => {
    let release: (r: Response) => void = () => {};
    const calls = serve(() => new Promise((resolve) => { release = resolve; }));
    render(<TelecallerAlertSettingsPanel />);
    const it = await screen.findByRole("region", { name: "IT team" });
    const button = within(it).getByRole("button", { name: "Save IT thresholds" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(button).toBeDisabled();
    release(res(row("it", "IT")));
    await waitFor(() => expect(button).not.toBeDisabled());
    expect(calls.filter((c) => c.init?.method === "PUT")).toHaveLength(1);
  });

  it("a failed load shows an error with a retry", async () => {
    let fail = true;
    serve(undefined, () => Promise.resolve(fail ? res({ detail: "Telecaller manager role required" }, 403) : res(settings)));
    render(<TelecallerAlertSettingsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Telecaller manager role required");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "IT team" })).toBeInTheDocument();
  });
});
