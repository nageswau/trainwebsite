import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentDetailPanel from "@/components/AgentStudentDetailPanel";
import type { AgentStudentDetail, Counseling } from "@/lib/agentStudents";

const base: AgentStudentDetail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: "Canada", preferred_intake: null, status: "active",
  assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "", counseling: null,
};
const recorded: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Law", course_preference: "LLM",
  country_preference: "Ireland", budget_amount: "2500000.00", budget_currency: "INR", remarks: "<script>alert(1)</script>\nSecond line",
  updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const counselingRegion = () => screen.getByRole("region", { name: "Counseling" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Counseling in the student detail panel (AGN-006)", () => {
  it("says when nothing is recorded and offers to record it", () => {
    render(<AgentStudentDetailPanel detail={base} onClose={vi.fn()} onSaved={vi.fn()} />);
    const region = counselingRegion();
    expect(within(region).getByText("Counseling not recorded yet.")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Record counseling" })).toBeInTheDocument();
  });

  it("shows the record in words, formats the budget and renders remarks as text", () => {
    render(<AgentStudentDetailPanel detail={{ ...base, counseling: recorded }} onClose={vi.fn()} onSaved={vi.fn()} />);
    const region = counselingRegion();
    expect(within(region).getByText(/^Yes — 01 Oct 2026, by Priya$/)).toBeInTheDocument();
    expect(within(region).getByText("₹25,00,000.00")).toBeInTheDocument();
    expect(within(region).getByText("Ireland")).toBeInTheDocument();
    expect(within(region).getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(within(region).getByRole("button", { name: "Edit counseling" })).toBeInTheDocument();
  });

  it("offers no counseling action for a student with a login or an archived student", () => {
    const { unmount } = render(<AgentStudentDetailPanel detail={{ ...base, has_login: true }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(within(counselingRegion()).getByText("Counseling is recorded only for students without a login.")).toBeInTheDocument();
    expect(within(counselingRegion()).queryByRole("button")).toBeNull();
    unmount();
    render(<AgentStudentDetailPanel detail={{ ...base, status: "archived", counseling: recorded }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(within(counselingRegion()).queryByRole("button")).toBeNull();
    expect(within(counselingRegion()).getByText("Law")).toBeInTheDocument();
  });

  it("keeps one form open at a time and Escape does not close the panel while one is open", async () => {
    const onClose = vi.fn();
    render(<AgentStudentDetailPanel detail={base} onClose={onClose} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Record counseling" }));
    expect(screen.getByRole("form", { name: "Record counseling for Asha" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("region", { name: "Asha" }), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Record counseling" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("button", { name: "Record counseling" })).toBeNull();
  });

  it("after a save shows the new record, reports it through the list notice and focuses the Counseling heading", async () => {
    const saved = { ...base, counseling: recorded };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ student: saved })));
    const onSaved = vi.fn();
    const { rerender } = render(<AgentStudentDetailPanel detail={base} onClose={vi.fn()} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Record counseling" }));
    fireEvent.change(screen.getByLabelText("Career interest"), { target: { value: "Law" } });
    fireEvent.click(screen.getByRole("button", { name: "Save counseling" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved, "Counseling saved for Asha."));
    rerender(<AgentStudentDetailPanel detail={saved} onClose={vi.fn()} onSaved={onSaved} />);
    expect(within(counselingRegion()).getByText("LLM")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Counseling" })).toHaveFocus());
  });
});
