import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMeetingReportForm from "@/components/BdmMeetingReportForm";

afterEach(cleanup);

describe("BdmMeetingReportForm", () => {
  it("needs an outcome and a discussion, then sends every field (blanks as null)", () => {
    const onSubmit = vi.fn();
    render(<BdmMeetingReportForm bdmType="college" mode="complete" busy={false} onSubmit={onSubmit} onCancel={() => {}} />);
    const save = screen.getByRole("button", { name: "Save report and complete" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "   " } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Keen on IT training\nwants fees" } });
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Send proposal" } });
    fireEvent.click(save);
    expect(onSubmit).toHaveBeenCalledWith({
      outcome: "interested", discussion: "Keen on IT training\nwants fees", requirements: null, opportunity: null,
      next_action: "Send proposal", responsible_person: null, next_follow_up_on: null,
    });
  });

  it("offers only the BDM type's outcomes", () => {
    render(<BdmMeetingReportForm bdmType="agent" mode="complete" busy={false} onSubmit={() => {}} onCancel={() => {}} />);
    const values = Array.from((screen.getByLabelText("Outcome (required)") as HTMLSelectElement).options).map((o) => o.value);
    expect(values).toContain("agreement_required");
    expect(values).not.toContain("course_promotion_interested");
  });

  it("prefills in edit mode, limits lengths, and shows field errors accessibly", () => {
    render(
      <BdmMeetingReportForm
        bdmType="college" mode="edit" busy={false} onSubmit={() => {}} onCancel={() => {}}
        initial={{ outcome: "interested", next_follow_up_on: "2030-01-10", report: { discussion: "Met", requirements: null, opportunity: "Lab", next_action: null, responsible_person: "Mrs Rao", legacy: false, author: { id: "u", full_name: "B", active: true }, submitted_at: "2030-01-01T05:00:00Z", updated_at: "2030-01-01T05:00:00Z" } }}
        errors={{ opportunity: "Opportunity contains invalid characters" }}
      />,
    );
    expect(screen.getByLabelText("Discussion (required)")).toHaveValue("Met");
    expect(screen.getByLabelText("Discussion (required)")).toHaveAttribute("maxLength", "4000");
    expect(screen.getByLabelText("Responsible person")).toHaveValue("Mrs Rao");
    expect(screen.getByLabelText("Next follow-up (IST date)")).toHaveValue("2030-01-10");
    const opportunity = screen.getByLabelText("Opportunity");
    expect(opportunity).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Opportunity contains invalid characters")).toHaveAttribute("id", opportunity.getAttribute("aria-describedby"));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });

  it("QA7-06: warns before the page is left with a typed report, and not for an untouched form", () => {
    render(<BdmMeetingReportForm bdmType="college" mode="complete" busy={false} onSubmit={() => {}} onCancel={() => {}} />);
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Half typed" } });
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });

  it("QA7-05: moves focus to the first invalid field when the server's field errors arrive", () => {
    const props = { bdmType: "college" as const, mode: "complete" as const, busy: false, onSubmit: () => {}, onCancel: () => {} };
    const { rerender } = render(<BdmMeetingReportForm {...props} />);
    rerender(<BdmMeetingReportForm {...props} errors={{ responsible_person: "Bad", opportunity: "Opportunity contains invalid characters" }} />);
    expect(document.activeElement).toBe(screen.getByLabelText("Opportunity"));
  });

  it("QA7-02: a locked form keeps the text readable and copyable but cannot be saved", () => {
    const onCancel = vi.fn();
    render(<BdmMeetingReportForm bdmType="college" mode="edit" busy={false} locked onSubmit={() => {}} onCancel={onCancel} initial={{ outcome: "interested", next_follow_up_on: null, report: null }} />);
    expect(screen.getByLabelText("Discussion (required)")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Outcome (required)")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("Escape cancels; busy disables saving", () => {
    const onCancel = vi.fn();
    render(<BdmMeetingReportForm bdmType="college" mode="complete" busy onSubmit={() => {}} onCancel={onCancel} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    fireEvent.keyDown(screen.getByLabelText("Outcome (required)"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
