import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffPermissionsForm from "@/components/AgentStaffPermissionsForm";

afterEach(cleanup);

function renderForm(busy = false) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  render(<AgentStaffPermissionsForm idPrefix="p-s1" name="Rahul Kumar" value={{ can_verify_documents: true, can_view_reports: false }} busy={busy} onSave={onSave} onCancel={onCancel} />);
  return { onSave, onCancel };
}

describe("AgentStaffPermissionsForm (AGN-003)", () => {
  it("labels each permission, explains it, and starts on the first box with the saved values", () => {
    renderForm();
    expect(screen.getByRole("group", { name: "What Rahul Kumar can do" })).toBeInTheDocument();
    const verify = screen.getByRole("checkbox", { name: "Verify documents" });
    const reports = screen.getByRole("checkbox", { name: "View reports" });
    expect(verify).toBeChecked();
    expect(reports).not.toBeChecked();
    expect(verify).toHaveFocus();
    expect(verify).toHaveAccessibleDescription("Mark pending documents as verified. Only Masters can reject or request changes.");
    expect(reports).toHaveAccessibleDescription("See the agency's application summary.");
  });

  it("saves both values", () => {
    const { onSave } = renderForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "View reports" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith({ can_verify_documents: true, can_view_reports: true });
  });

  it("Escape and Cancel cancel", () => {
    const { onCancel } = renderForm();
    fireEvent.keyDown(screen.getByRole("checkbox", { name: "Verify documents" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("shows Saving… and disables both buttons while busy", () => {
    renderForm(true);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});
