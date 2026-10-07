import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTargetsCard from "@/components/BdmTargetsCard";
import BdmTargetsCopy from "@/components/BdmTargetsCopy";
import BdmTargetsEditor from "@/components/BdmTargetsEditor";
import type { TargetSheet } from "@/lib/bdmTargets";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }) }));

const B1 = "00000000-0000-4000-8000-0000000000b1";
const sheet = (over: Partial<TargetSheet> = {}): TargetSheet => ({
  month: "2026-10", month_status: "current", editable: true, bdm: { id: B1, full_name: "Asha" }, bdm_type: "college",
  kpis: [
    { key: "college_meetings", label: "College Meetings", definition: "Your appointments at colleges completed this month.", tracked: true, target: 30, achieved: 22, percent: 73 },
    { key: "mous", label: "MoUs", definition: "MoUs you moved to Signed this month.", tracked: true, target: null, achieved: 1, percent: null },
    { key: "internship_students", label: "Internship Students", definition: "Not tracked: internships are not recorded in EduSphere.", tracked: false, target: 5, achieved: null, percent: null },
  ],
  ...over,
});
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("bdm-016 target editor", () => {
  it("shows target, achieved and percent per KPI; untracked says so and never shows 0", () => {
    render(<BdmTargetsEditor initial={sheet()} />);
    const row = (label: string) => screen.getByRole("rowheader", { name: new RegExp(label) }).closest("tr")!;
    expect((screen.getByLabelText("College Meetings target") as HTMLInputElement).value).toBe("30");
    expect(row("College Meetings").textContent).toContain("22");
    expect(row("College Meetings").textContent).toContain("73%");
    expect(row("MoUs").textContent).toContain("—");
    expect(row("Internship Students").textContent).toContain("Not tracked");
    expect(screen.getByText("Not tracked: internships are not recorded in EduSphere.")).toBeTruthy();
  });

  it("saves only the changed targets (blank clears), then re-reads the sheet", async () => {
    const saved = sheet({ kpis: sheet().kpis.map((k) => (k.key === "mous" ? { ...k, target: 4, percent: 25 } : k.key === "college_meetings" ? { ...k, target: null, percent: null } : k)) });
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => (url.endsWith("/manager/targets") ? res({ month: "2026-10", changed: 2 }) : res(saved)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTargetsEditor initial={sheet()} />);
    fireEvent.change(screen.getByLabelText("MoUs target"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("College Meetings target"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    fireEvent.click(screen.getByRole("button", { name: /Sav/ })); // a double click sends one PUT
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved 2 targets."));
    const puts = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
    expect(puts).toHaveLength(1);
    expect(JSON.parse((puts[0][1] as RequestInit).body as string)).toEqual({
      month: "2026-10",
      items: [{ bdm_user_id: B1, kpi_key: "college_meetings", target: null }, { bdm_user_id: B1, kpi_key: "mous", target: 4 }],
    });
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/bdm/manager/targets/${B1}?month=2026-10`);
    expect((screen.getByLabelText("MoUs target") as HTMLInputElement).value).toBe("4");
  });

  it("refuses a bad number before sending, and says when nothing changed", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTargetsEditor initial={sheet()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(screen.getByRole("status").textContent).toBe("No target changed.");
    fireEvent.change(screen.getByLabelText("MoUs target"), { target: { value: "2.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(screen.getByRole("alert").textContent).toBe("MoUs target must be a whole number from 0 to 100000.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API's refusal as its own sentence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ detail: "Past months' targets can only be changed by a super admin" }, 422)));
    render(<BdmTargetsEditor initial={sheet()} />);
    fireEvent.change(screen.getByLabelText("MoUs target"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Past months' targets can only be changed by a super admin"));
  });

  it("is read-only when not editable, and a future month has no achieved yet", () => {
    render(<BdmTargetsEditor initial={sheet({ editable: false, month_status: "future" })} />);
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save targets" })).toBeNull();
    expect(screen.getAllByText("Month not started").length).toBe(2);
    expect(screen.getByText("Not set")).toBeTruthy();
  });
});

describe("bdm-016 copy last month", () => {
  it("copies after the confirm and refreshes the page", async () => {
    const fetchMock = vi.fn(async () => res({ month: "2026-10", copied: 3 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTargetsCopy month="2026-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy last month's targets" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/September 2026/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yes, copy" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Copied 3 targets."));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/manager/targets/copy", expect.objectContaining({ method: "POST", body: JSON.stringify({ month: "2026-10" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("says when there was nothing to copy", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ month: "2026-10", copied: 0 })));
    render(<BdmTargetsCopy month="2026-10" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy last month's targets" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, copy" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Nothing to copy: every target from September 2026 is already set or there were none."));
  });
});

describe("bdm-016 My Day targets card", () => {
  it("lists the KPIs with a target as achieved / target and percent", () => {
    render(<BdmTargetsCard sheet={sheet()} />);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual(["College Meetings — 22 / 30 (73%)", "Internship Students — target 5 (not tracked)"]);
    expect(screen.getByRole("heading", { name: "Monthly targets — October 2026" })).toBeTruthy();
  });

  it("has an empty state and a failure state", () => {
    const { unmount } = render(<BdmTargetsCard sheet={sheet({ kpis: sheet().kpis.map((k) => ({ ...k, target: null })) })} />);
    expect(screen.getByText("No targets set for this month yet.")).toBeTruthy();
    unmount();
    render(<BdmTargetsCard sheet={null} />);
    expect(screen.getByText("Unable to load your targets right now.")).toBeTruthy();
  });
});
