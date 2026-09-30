import { fireEvent, type screen } from "@testing-library/react";

// ENH-031: pick an option in a SearchableSelect by its value (the id the old <select> used), as a user would: open, click.
export function pickOption(scope: Pick<typeof screen, "getByRole">, label: string, value: string): void {
  const input = scope.getByRole("combobox", { name: label });
  fireEvent.focus(input);
  const list = document.getElementById(input.getAttribute("aria-controls") ?? "");
  const option = list?.querySelector<HTMLElement>(`[data-value="${value}"]`);
  if (!option) throw new Error(`No option with value "${value}" in "${label}"`);
  fireEvent.click(option);
}
