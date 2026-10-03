import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FormMessage from "@/components/FormMessage";
import { NOT_COMPLETED } from "@/lib/apiErrors";
import type { Trip } from "@/lib/bdmTravel";
import { TripLiveContext } from "@/lib/tripLive";
import { useTripWrite } from "@/lib/useTripWrite";

import { json, trip } from "../components/tripFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function Panel({ name, url }: { name: string; url: string }) {
  const { busy, message, run, resultProps } = useTripWrite();
  return (
    <section aria-label={name}>
      <button type="button" disabled={busy} onClick={() => run(url, { method: "POST" }, `${name} done.`)}>{name}</button>
      <div {...resultProps}>{message && <FormMessage message={message} />}</div>
    </section>
  );
}

beforeEach(() => {
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useTripWrite (bdm-010 QA fixes)", () => {
  it("QA10-06: a server error reads as 'did not complete' and focus moves to the result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    render(<Panel name="Submit" url="/x" />);
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    await waitFor(() => expect(screen.getByRole("alert").parentElement).toHaveFocus());
  });

  it("QA10-09: starting a write in one panel clears the result another panel shows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true })));
    render(<><Panel name="Delete" url="/a" /><Panel name="Remarks" url="/b" /></>);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Delete done.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remarks" }));
    expect(await screen.findByText("Remarks done.")).toBeInTheDocument();
    expect(screen.queryByText("Delete done.")).toBeNull();
  });

  it("QA10-16: inside a live trip a success applies the returned trip instead of refreshing; a 409 re-reads it", async () => {
    const apply = vi.fn();
    const reload = vi.fn().mockResolvedValue(undefined);
    const updated: Trip = trip({ approval_status: "submitted" });
    const mock = vi.fn().mockResolvedValueOnce(json(updated)).mockResolvedValueOnce(json({ detail: "This trip is already approved and can't be withdrawn" }, 409));
    vi.stubGlobal("fetch", mock);
    render(<TripLiveContext.Provider value={{ apply, reload }}><Panel name="Go" url="/x" /></TripLiveContext.Provider>);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(apply).toHaveBeenCalledWith(updated));
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    await act(async () => undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
