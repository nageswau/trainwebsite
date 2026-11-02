import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminCertificatePanel from "@/components/AdminCertificatePanel";
import AttendanceCorrectionPanel from "@/components/AttendanceCorrectionPanel";
import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";
import { classesParts } from "@/lib/hrStudents";
import { itAttendanceLabel } from "@/lib/itAttendance";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

// itc-021 (DEC-SCOPE-349): IT attendance's stored "excused" is shown as "Approved leave" everywhere, and the admin sets how it counts.
const RULES = "/api/v1/workflows/it/certificates/rules";
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IT attendance labels", () => {
  it("names excused as Approved leave and keeps the others", () => {
    expect(["present", "absent", "late", "excused"].map(itAttendanceLabel)).toEqual(["Present", "Absent", "Late", "Approved leave"]);
  });

  it("the HR view counts approved leave by name", () => {
    expect(classesParts({ marked: 12, present: 9, late: 0, excused: 1, absent: 2, attendance_pct: 75 })).toEqual(["Present 9", "Late 0", "Approved leave 1", "Absent 2 (12 marked)"]);
  });

  it("the student's sessions and the correction choices say Approved leave", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([{ id: "a1", batch: "Batch A", session_date: "2026-10-20", status: "excused", notes: null, correction_pending: false }])));
    render(<AttendanceCorrectionPanel />);
    const row = (await screen.findByText("Batch A")).closest("tr")!;
    expect(within(row).getByText("Approved leave")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: /request correction/i }));
    const status = screen.getByLabelText("Correct status") as HTMLSelectElement;
    expect(Array.from(status.options).map((o) => o.textContent)).toEqual(["Present", "Absent", "Late"]);
  });

  it("the trainer's register offers Approved leave (stored as excused)", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => json(url.endsWith("/trainer/context")
      ? { batches: [{ id: "b1", name: "Batch A" }], students: [{ id: "s1", name: "Asha", batch_id: "b1" }] }
      : [])));
    render(<TeacherWorkspaceActions section="attendance" />);
    const select = (await screen.findByLabelText("Asha status")) as HTMLSelectElement;
    const leave = Array.from(select.options).find((o) => o.value === "excused");
    expect(leave?.textContent).toBe("Approved leave");
  });
});

describe("admin leave policy (certificate rules panel)", () => {
  it("shows the stored policy and saves a change with the thresholds", async () => {
    const mock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? json(JSON.parse(String(init.body))) : json({ min_progress_percent: 100, min_attendance_percent: 75, leave_policy: "attended" })));
    vi.stubGlobal("fetch", mock);
    render(<AdminCertificatePanel />);
    const policy = (await screen.findByLabelText("Approved leave counts as")) as HTMLSelectElement;
    await waitFor(() => expect(policy).toHaveValue("attended"));
    expect(Array.from(policy.options).map((o) => o.value)).toEqual(["attended", "excluded", "absent"]);
    fireEvent.change(policy, { target: { value: "excluded" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Certificate rules saved. They apply to the next eligibility check.")).toBeInTheDocument();
    const put = mock.mock.calls.find(([url, init]) => url === RULES && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ min_progress_percent: 100, min_attendance_percent: 75, leave_policy: "excluded" });
    expect(screen.getByLabelText("Approved leave counts as")).toHaveValue("excluded");
  });
});
