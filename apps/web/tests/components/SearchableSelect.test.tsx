import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SearchableSelect, { DEBOUNCE_MS } from "@/components/SearchableSelect";
import type { LookupPage } from "@/lib/lookups";

const OPTIONS = [
  { id: "s1", label: "Asha Rao", detail: "Hill School" },
  { id: "s2", label: "Ravi Iyer", detail: "Lake School" },
  { id: "s3", label: "Meera Das", detail: "Hill School" },
];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function inForm(ui: ReactNode) {
  render(<form data-testid="form">{ui}</form>);
  return { form: screen.getByTestId("form") as HTMLFormElement, input: screen.getByRole("combobox") as HTMLInputElement };
}

const hidden = (form: HTMLFormElement, name: string) => new FormData(form).get(name);

describe("SearchableSelect load-once mode", () => {
  it("filters by label or detail and submits only the picked id", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="school_student_id" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "hill" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Asha Rao — Hill School", "Meera Das — Hill School"]);
    fireEvent.click(screen.getByRole("option", { name: "Meera Das — Hill School" }));
    expect(input.value).toBe("Meera Das — Hill School");
    expect(hidden(form, "school_student_id")).toBe("s3");
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("supports the keyboard: ArrowDown moves, Enter picks, Escape closes", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[1].id);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(hidden(form, "sid")).toBe("s2");
    fireEvent.change(input, { target: { value: "a" } });
    expect(input).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("wires the combobox to its listbox", () => {
    const { input } = inForm(<SearchableSelect id="psych-student" label="Student" noun="student" options={OPTIONS} />);
    expect(input.id).toBe("psych-student");
    expect(input.getAttribute("aria-controls")).toBe("psych-student-list");
    fireEvent.focus(input);
    expect(screen.getByRole("listbox", { name: "Student" }).id).toBe("psych-student-list");
  });

  it("a required field without a pick is invalid and shows the field error", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" required noun="student" options={OPTIONS} />);
    let valid = true;
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(false);
    expect(screen.getByText("Choose a student from the list.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("an optional field is valid when empty but not with unpicked text", () => {
    const { form, input } = inForm(<SearchableSelect label="Application" name="aid" noun="application" options={OPTIONS} />);
    let valid = false;
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(true);
    fireEvent.change(input, { target: { value: "Asha Rao" } });
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(false);
    expect(screen.getByText("Choose an application from the list.")).toBeInTheDocument();
  });

  it("editing after a pick clears the pick and tells the host", () => {
    const onChange = vi.fn();
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} onChange={onChange} />);
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "Asha Rao — Hill School" }));
    expect(onChange).toHaveBeenLastCalledWith(OPTIONS[0]);
    fireEvent.change(input, { target: { value: "Asha Ra" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(hidden(form, "sid")).toBe("");
  });

  it("a form reset clears the text and the pick", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "Asha Rao — Hill School" }));
    act(() => form.reset());
    expect(input.value).toBe("");
    expect(hidden(form, "sid")).toBe("");
  });

  it("renders at most 50 options and asks to keep typing", () => {
    const many = Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, label: `Student ${i}` }));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" options={many} />);
    fireEvent.focus(input);
    expect(screen.getAllByRole("option")).toHaveLength(50);
    expect(screen.getByText("Keep typing to narrow the list.")).toBeInTheDocument();
  });

  it("says when nothing matches, and never adds a role=status element", () => {
    const { input } = inForm(<SearchableSelect label="Student" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.getByText("No matching students.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("SearchableSelect server mode", () => {
  const page = (...labels: string[]): LookupPage => ({ items: labels.map((label, i) => ({ id: `r${i}`, label })), truncated: false });

  it("waits for minChars, then searches once after the debounce", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockResolvedValue(page("Asha Rao"));
    const { input } = inForm(<SearchableSelect label="Overseas student reference" noun="student" search={search} minChars={3} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "as" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).not.toHaveBeenCalled();
    expect(screen.getByText("Type at least 3 characters.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ash" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).toHaveBeenCalledTimes(1);
    expect(search.mock.calls[0][0]).toBe("ash");
    expect(screen.getByRole("option", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("ignores a slow reply for an older query", async () => {
    vi.useFakeTimers();
    let resolveOld: (value: LookupPage) => void = () => {};
    const search = vi.fn()
      .mockImplementationOnce(() => new Promise<LookupPage>((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce(page("New Result"));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "old" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    fireEvent.change(input, { target: { value: "new" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    await act(async () => { resolveOld(page("Old Result")); });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["New Result"]);
  });

  it("shows a failure with Retry, and Retry searches again", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(page("Asha Rao"));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ash" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(screen.getByText("Could not load the students.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("option", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("reports a truncated result", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockResolvedValue({ ...page("Asha Rao"), truncated: true });
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(screen.getByText("Keep typing to narrow the list.")).toBeInTheDocument();
  });
});
