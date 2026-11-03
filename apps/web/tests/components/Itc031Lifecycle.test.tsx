import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ItLifecycleCard from "@/components/ItLifecycleCard";
import { stageTone, type LifecycleEnrollment, type LifecycleResponse } from "@/lib/itLifecycle";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const STUDENT = "s-1";
const base: LifecycleEnrollment = {
  enrollment_id: "e-1", enrollment_code: "EDU-1", program: "Python Full Stack", batch: "PY-JAN", stage: "training_active", stage_label: "Training active",
  components: { fee: { stage: "fee_pending", stage_label: "Fee pending" }, training: { stage: "training_active", stage_label: "Training active" }, placement: null },
  override: null,
  history: [{ from_stage: "fee_pending", from_label: "Fee pending", to_stage: "training_active", to_label: "Training active", cause: "daily_check", actor: null, created_at: "2026-11-02T04:00:00Z" }],
};
const data = (e: Partial<LifecycleEnrollment> = {}): LifecycleResponse => ({ enrollments: [{ ...base, ...e }] });
const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });

describe("itc-031 lifecycle card (DEC-SCOPE-358)", () => {
  it("shows the stage, the concurrent components and the history with actor and cause", () => {
    render(<ItLifecycleCard initial={data()} studentId={STUDENT} canOverride={false} />);
    expect(screen.getByTestId("lifecycle-stage")).toHaveTextContent("Training active");
    expect(screen.getByText("Fee pending")).toBeInTheDocument(); // E: Fee Pending stays visible beside Training Active
    expect(screen.getByText("Not started")).toBeInTheDocument();
    const history = screen.getByRole("list", { name: "Lifecycle history for EDU-1" });
    expect(within(history).getByText(/Fee pending → Training active · Daily check · System/)).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument(); // the counselor reads only
  });

  it("explains an empty history and an empty enrolment list", () => {
    const { unmount } = render(<ItLifecycleCard initial={data({ history: [] })} studentId={STUDENT} canOverride={false} />);
    expect(screen.getByText(/No changes recorded yet/)).toBeInTheDocument();
    unmount();
    render(<ItLifecycleCard initial={{ enrollments: [] }} studentId={STUDENT} canOverride={false} />);
    expect(screen.getByText("No enrolments yet.")).toBeInTheDocument();
  });

  it("lets the IT Admin set Not placed with a reason and shows the new stage", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(data({ stage: "not_placed", stage_label: "Not placed", override: { stage: "not_placed", stage_label: "Not placed", reason: "No offers" } })));
    render(<ItLifecycleCard initial={data()} studentId={STUDENT} canOverride />);
    fireEvent.change(screen.getByLabelText("Set by hand"), { target: { value: "not_placed" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "No offers" } });
    fireEvent.click(screen.getByRole("button", { name: "Save stage" }));
    expect(await screen.findByText("Stage saved.")).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe("/api/v1/admin/it/students/s-1/enrollments/e-1/lifecycle-override");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({ stage: "not_placed", reason: "No offers" });
    expect(screen.getByTestId("lifecycle-stage")).toHaveTextContent("Not placed");
    expect(screen.getByTestId("lifecycle-override")).toHaveTextContent("Set by the IT Admin: Not placed (No offers)");
    expect(screen.getByRole("button", { name: "Clear hand-set stage" })).toBeInTheDocument();
  });

  it("checks the choice and the reason before sending", () => {
    render(<ItLifecycleCard initial={data()} studentId={STUDENT} canOverride />);
    fireEvent.click(screen.getByRole("button", { name: "Save stage" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose Not placed or Closed.");
    fireEvent.change(screen.getByLabelText("Set by hand"), { target: { value: "closed" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: " a " } });
    fireEvent.click(screen.getByRole("button", { name: "Save stage" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Give a reason of at least 3 characters.");
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("shows the server's refusal and keeps the entries", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "The student has a joining record, so the stage is Placed" }), { status: 409 }));
    render(<ItLifecycleCard initial={data()} studentId={STUDENT} canOverride />);
    fireEvent.change(screen.getByLabelText("Set by hand"), { target: { value: "not_placed" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "No offer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save stage" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The student has a joining record, so the stage is Placed");
    expect(screen.getByLabelText("Reason")).toHaveValue("No offer");
  });

  it("clears a hand-set stage", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(data()));
    render(<ItLifecycleCard initial={data({ stage: "closed", stage_label: "Closed", override: { stage: "closed", stage_label: "Closed", reason: "Left" } })} studentId={STUDENT} canOverride />);
    fireEvent.click(screen.getByRole("button", { name: "Clear hand-set stage" }));
    expect(await screen.findByText("Hand-set stage cleared.")).toBeInTheDocument();
    expect(JSON.parse(vi.mocked(global.fetch).mock.calls[0][1]?.body as string)).toEqual({ stage: null });
    expect(screen.queryByTestId("lifecycle-override")).not.toBeInTheDocument();
  });

  it("tones never stand alone: at risk is red, closed muted, fee states amber", () => {
    expect(stageTone("at_risk")).toBe("status error");
    expect(stageTone("closed")).toBe("status closed");
    expect(stageTone("partially_paid")).toBe("status pending");
    expect(stageTone("placed")).toBe("status");
  });
});
