import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItAtRiskList from "@/components/ItAtRiskList";
import PortalSection from "@/components/PortalSection";
import TrainerBatchFilter from "@/components/TrainerBatchFilter";
import type { PortalPayload } from "@/lib/types";

// itc-024 (DEC-SCOPE-355): the trainer dashboard's batch filter, its "No classes today" panel and the at-risk list narrowed to the batch.
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/it/trainer/dashboard" }));

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const OPTIONS = [{ value: "b1", label: "FSJ-Nov" }, { value: "b2", label: "PY-Dec" }];
const flag = (id: string, batch: string, name: string) => ({
  id, student: { id: `s-${id}`, full_name: name, student_code: null }, program: "Full Stack Java", batch: { id: batch, name: batch },
  reasons: ["attendance"], attendance_percent: "60.00", assessment_percent: null, consecutive_absences: 0,
  raised_at: "2026-11-02T01:30:00Z", cleared_at: null, clear_reason: null, profile_url: null,
});

afterEach(() => {
  cleanup();
  push.mockReset();
  vi.unstubAllGlobals();
});

describe("trainer batch filter", () => {
  it("lists the trainer's batches under a labelled select and puts the choice in the address", () => {
    render(<TrainerBatchFilter filter={{ value: null, options: OPTIONS }} />);
    const select = screen.getByLabelText("Batch") as HTMLSelectElement;
    expect([...select.options].map((o) => o.text)).toEqual(["All batches", "FSJ-Nov", "PY-Dec"]);
    fireEvent.change(select, { target: { value: "b2" } });
    expect(push).toHaveBeenCalledWith("/it/trainer/dashboard?batch=b2");
  });

  it("goes back to every batch and shows a refused filter's message", () => {
    render(<TrainerBatchFilter filter={{ value: "b1", options: OPTIONS }} error="Choose one of your batches" />);
    expect(screen.getByRole("alert").textContent).toBe("Choose one of your batches");
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "" } });
    expect(push).toHaveBeenCalledWith("/it/trainer/dashboard");
  });
});

describe("dashboard panels", () => {
  it("says so when a panel has nothing to list", () => {
    const data: PortalPayload = { title: "Trainer Dashboard", subtitle: "", metrics: [], actions: [], columns: [], rows: [], panels: [{ title: "Today's classes", items: [], empty: "No classes today" }] };
    render(<PortalSection data={data} table={false} />);
    expect(screen.getByRole("heading", { name: "Today's classes" })).toBeTruthy();
    expect(screen.getByText("No classes today")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });
});

describe("at-risk list for one batch", () => {
  it("keeps only the chosen batch's students", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([flag("f1", "b1", "Asha Rao"), flag("f2", "b2", "Ravi Kumar")])));
    render(<ItAtRiskList batchId="b2" />);
    expect(await screen.findByText("Ravi Kumar")).toBeTruthy();
    expect(screen.queryByText("Asha Rao")).toBeNull();
  });
});
