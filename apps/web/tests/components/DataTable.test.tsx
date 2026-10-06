import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DataTable from "@/components/DataTable";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(cleanup);

describe("DataTable assign_counselor column", () => {
  it("renders Assign or Change counsellor per row", () => {
    render(
      <DataTable
        columns={[{ key: "student", label: "Student" }, { key: "assign", label: "", type: "assign_counselor" }]}
        rows={[
          { id: "a1", student: "Asha", counselor_id: null, assign: "a1" },
          { id: "a2", student: "Ravi", counselor_id: "c1", assign: "a2" },
        ]}
        label="Applications"
      />,
    );
    const asha = screen.getByText("Asha").closest("tr") as HTMLElement;
    const ravi = screen.getByText("Ravi").closest("tr") as HTMLElement;
    expect(within(asha).getByRole("button", { name: "Assign counsellor" })).toBeTruthy();
    expect(within(ravi).getByRole("button", { name: "Change counsellor" })).toBeTruthy();
  });

  it("renders no control on a closed row (assign is null)", () => {
    render(
      <DataTable
        columns={[{ key: "student", label: "Student" }, { key: "assign", label: "", type: "assign_counselor" }]}
        rows={[
          { id: "a1", student: "Asha", counselor_id: "c1", assign: null },
          { id: "a2", student: "Ravi", counselor_id: null, assign: "a2" },
        ]}
        label="Applications"
      />,
    );
    const asha = screen.getByText("Asha").closest("tr") as HTMLElement;
    const ravi = screen.getByText("Ravi").closest("tr") as HTMLElement;
    expect(within(asha).queryByRole("button")).toBeNull();
    expect(within(ravi).getByRole("button", { name: "Assign counsellor" })).toBeTruthy();
  });
});
