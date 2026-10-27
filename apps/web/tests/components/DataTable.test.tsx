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

// nehn-027 (DEC-SCOPE-294 M8): the student Downloads table opens each material; only web and API addresses become links.
describe("DataTable link column", () => {
  it("links web and download-route values and leaves anything else as text", () => {
    render(
      <DataTable
        columns={[{ key: "title", label: "Resource" }, { key: "url", label: "Download", type: "link" }]}
        rows={[
          { title: "Week 1 notes", url: "/api/v1/workflows/it/materials/m1/file" },
          { title: "Recording", url: "https://youtu.be/abc" },
          { title: "Legacy", url: "javascript:alert(1)" },
        ]}
        label="Downloads"
      />,
    );
    const notes = screen.getByText("Week 1 notes").closest("tr") as HTMLElement;
    expect(within(notes).getByRole("link", { name: "Open Week 1 notes" }).getAttribute("href")).toBe("/api/v1/workflows/it/materials/m1/file");
    const recording = within(screen.getByText("Recording").closest("tr") as HTMLElement).getByRole("link", { name: "Open Recording" });
    expect(recording.getAttribute("target")).toBe("_blank");
    expect(recording.getAttribute("rel")).toContain("noopener");
    const legacy = screen.getByText("Legacy").closest("tr") as HTMLElement;
    expect(within(legacy).queryByRole("link")).toBeNull();
    expect(within(legacy).getByText("javascript:alert(1)")).toBeTruthy();
  });
});
