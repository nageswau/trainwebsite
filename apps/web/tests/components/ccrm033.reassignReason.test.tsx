import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignCounselorButton from "@/components/AssignCounselorButton";
import { timelineEntry, type TimelineRow } from "@/lib/leadTimeline";

// ccrm-033 (DEC-SCOPE-271, RR1): a reason is required when a counsellor is replaced, optional on a first assignment.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const PAGE = { items: [{ id: "c2", label: "Asha Rao", detail: null }], truncated: false };

function stub() {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
    init?.method === "PUT" ? json(200, { id: "a1", counselor_id: "c2", counselor_name: "Asha Rao", changed: true }) : json(200, PAGE));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function choose() {
  fireEvent.change(await screen.findByRole("combobox", { name: "EduSphere counsellor" }), { target: { value: "Asha" } });
  fireEvent.click(await screen.findByRole("option", { name: /Asha Rao/ }));
}

describe("AssignCounselorButton reason (ccrm-033)", () => {
  it("requires a reason to change the counsellor and sends it trimmed", async () => {
    const fetchMock = stub();
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    await choose();
    const reason = screen.getByRole("textbox", { name: "Reason for the change" });
    // QA33-01 / QA33-02: the field uses the app's field style and the in-row form keeps a usable width
    expect(reason.closest(".field")).not.toBeNull();
    expect((screen.getByRole("form", { name: "Change counsellor" }) as HTMLFormElement).style.minWidth).toBe("min(18rem, 70vw)");
    expect(reason).toBeRequired();
    expect(reason).toHaveAttribute("maxLength", "500");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(reason, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(reason, { target: { value: "  Counsellor on leave " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Rao assigned.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/applications/a1/counselor",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c2", reason: "Counsellor on leave" }) }));
  });

  it("makes the reason optional on a first assignment", async () => {
    const fetchMock = stub();
    render(<AssignCounselorButton applicationId="a1" currentId={null} url="/api/v1/admin/users/s1/counselor" />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    const reason = screen.getByRole("textbox", { name: "Reason (optional)" });
    expect(reason).not.toBeRequired();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    fireEvent.change(reason, { target: { value: "New intake" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/users/s1/counselor",
      expect.objectContaining({ body: JSON.stringify({ counselor_id: "c2", reason: "New intake" }) }));
  });
});

describe("lead timeline counsellor change (ccrm-033 RR3)", () => {
  const row = (over: Partial<TimelineRow>) => ({ kind: "handover", from_value: "u1", from_label: "Ravi", to_value: "", to_label: "", reason: "Lead paused", ...over }) as TimelineRow;

  it("titles a removal and shows the reason", () => {
    const entry = timelineEntry(row({}));
    expect(entry.title).toBe("Counselor removed (was Ravi)");
    expect(entry.detail).toBe("Lead paused");
  });

  it("keeps the change title", () => {
    expect(timelineEntry(row({ to_value: "u2", to_label: "Asha" })).title).toBe("Counselor changed from Ravi to Asha");
  });
});
