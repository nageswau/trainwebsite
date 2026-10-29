import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import IntakePicker, { intakeProblem, isIntake } from "@/components/IntakePicker";

const YEAR = new Date().getFullYear();

function Harness({ start = "", onValue }: { start?: string; onValue?: (v: string) => void }) {
  const [value, setValue] = useState(start);
  return <IntakePicker id="t-intake" label="Intake" value={value} onChange={(v) => { setValue(v); onValue?.(v); }} />;
}

afterEach(cleanup);

describe("IntakePicker (ccrm-047)", () => {
  it("offers the twelve months and this year to three years ahead", () => {
    render(<Harness />);
    const month = screen.getByLabelText("Intake month");
    const year = screen.getByLabelText("Intake year");
    expect(screen.getByRole("group", { name: "Intake" })).toBeInTheDocument();
    // QA-01: the legend reads like every other field label (`.field label`: 800, 13px)
    expect(screen.getByText("Intake", { selector: "legend" })).toHaveStyle({ fontWeight: "800", fontSize: "13px" });
    expect([...month.querySelectorAll("option")].map((o) => o.value)).toEqual(["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]);
    expect([...year.querySelectorAll("option")].map((o) => o.value)).toEqual(["", ...[0, 1, 2, 3].map((n) => String(YEAR + n))]);
  });

  it("writes Month YYYY once both parts are chosen and clears to empty", () => {
    const seen: string[] = [];
    render(<Harness onValue={(v) => seen.push(v)} />);
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Sep" } });
    fireEvent.change(screen.getByLabelText("Intake year"), { target: { value: String(YEAR + 1) } });
    expect(seen.at(-1)).toBe(`Sep ${YEAR + 1}`);
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Intake year"), { target: { value: "" } });
    expect(seen.at(-1)).toBe("");
  });

  it("shows a saved value, even a year outside the offered range", () => {
    render(<Harness start="Jan 2020" />);
    expect(screen.getByLabelText("Intake month")).toHaveValue("Jan");
    expect(screen.getByLabelText("Intake year")).toHaveValue("2020");
  });

  it("keeps a legacy free-text value and says how to replace it", () => {
    render(<Harness start="September next year" />);
    expect(screen.getByText(/Saved as “September next year”/)).toBeInTheDocument();
    expect(screen.getByLabelText("Intake month")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Oct" } });
    expect(screen.queryByText(/Saved as/)).not.toBeInTheDocument();
  });

  it("checks values: complete, half-chosen, and an untouched saved value", () => {
    expect(isIntake("Sep 2027")).toBe(true);
    expect(isIntake("September 2027")).toBe(false);
    expect(intakeProblem("")).toBeNull();
    expect(intakeProblem("Sep 2027")).toBeNull();
    expect(intakeProblem("Sep")).toBe("Choose both the month and the year for the intake.");
    expect(intakeProblem("2027")).toBe("Choose both the month and the year for the intake.");
    expect(intakeProblem("Fall 2027", "Fall 2027")).toBeNull();
  });
});
