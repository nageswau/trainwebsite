import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import StaleRecordNotice from "@/components/StaleRecordNotice";
import { reapply, staleConflict, staleSummary, useStaleGuard } from "@/lib/staleGuard";

// hrc-003 (DEC-SCOPE-370 S3, S7): the 409 `record_changed` parser, the re-apply rule, the guard hook and the notice.
afterEach(cleanup);

const detail = (over: Record<string, unknown> = {}) => ({
  code: "record_changed", message: "This record changed since you opened it", changed_by: { id: "u2", full_name: "Priya Admin" },
  changed_at: "2026-11-04T04:45:00.123456+00:00", changed_fields: ["title"], current: { title: "Theirs", location: "Pune", updated_at: "T2" }, ...over,
});
const refused = (over: Record<string, unknown> = {}) => ({ ok: false as const, status: 409, message: "x", detail: detail(over) });

describe("staleConflict", () => {
  it("reads a record_changed 409 and ignores every other failure", () => {
    expect(staleConflict(refused())).toEqual({ changedBy: "Priya Admin", changedAt: "2026-11-04T04:45:00.123456+00:00", changedFields: ["title"], current: detail().current });
    expect(staleConflict({ ok: false, status: 409, detail: "This candidate is archived" })).toBeNull();
    expect(staleConflict({ ok: false, status: 422, detail: detail() })).toBeNull();
    expect(staleConflict(refused({ current: null }))).toBeNull();
    expect(staleConflict({ ok: true })).toBeNull();
  });

  it("summarises who and when in IST, and only what is known", () => {
    expect(staleSummary(staleConflict(refused())!)).toBe("This record changed since you opened it (by Priya Admin at 04 Nov 2026, 10:15 IST).");
    expect(staleSummary(staleConflict(refused({ changed_by: null, changed_at: null }))!)).toBe("This record changed since you opened it.");
  });
});

describe("reapply", () => {
  it("puts only the user's own edits over the latest values and lists them", () => {
    const opened = { title: "A", location: "Pune", notes: "x" };
    const latest = { title: "B", location: "Chennai", notes: "x" };
    const mine = { title: "A", location: "Hyderabad", notes: "y" };
    expect(reapply(latest, opened, mine)).toEqual({
      values: { title: "B", location: "Hyderabad", notes: "y" },
      review: [{ key: "location", yours: "Hyderabad", now: "Chennai", alsoChanged: true }, { key: "notes", yours: "y", now: "x", alsoChanged: false }],
    });
  });
});

describe("useStaleGuard", () => {
  type Rec = { title: string; location: string; updated_at: string };
  const toValues = (r?: Rec) => ({ title: r?.title ?? "", location: r?.location ?? "" });
  const tokenOf = (r?: Rec) => r?.updated_at ?? null;
  const start = () => renderHook(() => useStaleGuard<Rec, { title: string; location: string }>({ title: "Mine", location: "Pune", updated_at: "T1" }, toValues, tokenOf));

  it("Reload drops the edits and takes the latest token", () => {
    const { result } = start();
    act(() => result.current.setValues({ title: "Edited", location: "Pune" }));
    act(() => void result.current.caught(refused()));
    expect(result.current.conflict?.changedBy).toBe("Priya Admin");
    act(() => void result.current.reload());
    expect(result.current.values).toEqual({ title: "Theirs", location: "Pune" });
    expect(result.current.token).toBe("T2");
    expect(result.current.conflict).toBeNull();
  });

  it("Review keeps the user's edits over the latest values and lists them", () => {
    const { result } = start();
    act(() => result.current.setValues({ title: "Mine", location: "Hyderabad" }));
    act(() => void result.current.caught(refused()));
    act(() => void result.current.reviewMine());
    expect(result.current.values).toEqual({ title: "Theirs", location: "Hyderabad" });
    expect(result.current.opened).toEqual({ title: "Theirs", location: "Pune" });
    expect(result.current.token).toBe("T2");
    expect(result.current.review).toEqual([{ key: "location", yours: "Hyderabad", now: "Pune", alsoChanged: false }]);
  });

  it("another failure is not caught", () => {
    const { result } = start();
    let caught = true;
    act(() => void (caught = result.current.caught({ ok: false, status: 409, detail: "Decided" })));
    expect(caught).toBe(false);
    expect(result.current.conflict).toBeNull();
  });
});

describe("StaleRecordNotice", () => {
  const labelOf = (f: string) => ({ title: "Job title", location: "Job location" })[f] ?? f;

  it("shows who/when/what with Review and Reload, and takes focus", () => {
    const onReload = vi.fn();
    const onReview = vi.fn();
    render(<StaleRecordNotice guard={{ conflict: staleConflict(refused({ changed_fields: ["title", "location"] })), review: null }} labelOf={labelOf} onReload={onReload} onReview={onReview} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("This record changed since you opened it (by Priya Admin at 04 Nov 2026, 10:15 IST).");
    expect(alert).toHaveTextContent("Changed: Job title, Job location.");
    expect(alert).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Review my changes" }));
    fireEvent.click(screen.getByRole("button", { name: "Reload latest" }));
    expect(onReview).toHaveBeenCalledTimes(1);
    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it("lists the re-applied changes, flagging the ones someone else also changed", () => {
    render(
      <StaleRecordNotice guard={{ conflict: null, review: [{ key: "location", yours: "Hyderabad", now: "", alsoChanged: true }] }} labelOf={labelOf}
        display={(_k, v) => v.toUpperCase()} onReload={vi.fn()} onReview={vi.fn()} />,
    );
    const list = screen.getByRole("list", { name: "Your changes" });
    expect(list).toHaveTextContent("Job location: yours “HYDERABAD”, now on record empty");
    expect(list).toHaveTextContent("also changed by someone else");
  });

  it("renders nothing without a conflict or a review", () => {
    const { container } = render(<StaleRecordNotice guard={{ conflict: null, review: null }} labelOf={labelOf} onReload={vi.fn()} onReview={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
