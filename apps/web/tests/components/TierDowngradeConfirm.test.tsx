import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TierDowngradeConfirm from "@/components/TierDowngradeConfirm";

afterEach(cleanup);

const lost = [{ key: "visa_support", label: "Visa support" }, { key: "internships", label: "Internships" }];

function renderBlock(overrides: Partial<Parameters<typeof TierDowngradeConfirm>[0]> = {}) {
  const props = { schoolName: "Oak School", fromTier: "Platinum", toTier: "Gold", lost, busy: false, onConfirm: vi.fn(), onCancel: vi.fn(), ...overrides };
  render(<TierDowngradeConfirm {...props} />);
  return props;
}

describe("TierDowngradeConfirm", () => {
  it("states the downgrade and lists every lost service", () => {
    renderBlock();
    const group = screen.getByRole("group", { name: "Downgrading Oak School from Platinum to Gold." });
    expect(within(group).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Visa support", "Internships"]);
    expect(within(group).getByText("Work already started can still be completed. The school will be notified.")).toBeTruthy();
  });

  it("puts focus on Confirm, which is described by the consequences", () => {
    renderBlock();
    const confirm = screen.getByRole("button", { name: "Confirm downgrade" });
    expect(confirm).toHaveFocus();
    expect(confirm).toHaveAccessibleDescription(/These services will no longer be available for new work:/);
  });

  it("Escape and Cancel both cancel; Confirm confirms", () => {
    const props = renderBlock();
    fireEvent.keyDown(screen.getByRole("button", { name: "Confirm downgrade" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Confirm downgrade" }));
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("while busy both buttons are disabled, Confirm says Saving and Escape does nothing", () => {
    const props = renderBlock({ busy: true });
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("group"), { key: "Escape" });
    expect(props.onCancel).not.toHaveBeenCalled();
  });
});
