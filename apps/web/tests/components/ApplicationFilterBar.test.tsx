import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationFilterBar from "@/components/ApplicationFilterBar";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/overseas/admin/applications" }));

afterEach(() => {
  cleanup();
  push.mockReset();
});

const ADMIN = {
  agency: null,
  counselor: null,
  agencies: [{ value: "org1", label: "Demo Global Education" }],
  counselors: [{ value: "c1", label: "Asha Rao" }, { value: "c2", label: "Old Hand (inactive)" }],
};

describe("ApplicationFilterBar", () => {
  it("puts the chosen agency in the URL and keeps the counselor", () => {
    render(<ApplicationFilterBar filters={{ ...ADMIN, counselor: "none" }} />);
    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "org1" } });
    expect(push).toHaveBeenCalledWith("/overseas/admin/applications?agency=org1&counselor=none");
  });

  it("offers All, Any agency, Not from an agency and each agency", () => {
    render(<ApplicationFilterBar filters={ADMIN} />);
    const options = Array.from((screen.getByLabelText("Agency") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(options).toEqual(["All", "Any agency", "Not from an agency", "Demo Global Education"]);
    const counselors = Array.from((screen.getByLabelText("Counsellor") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(counselors).toEqual(["All", "Not assigned", "Asha Rao", "Old Hand (inactive)"]);
  });

  it("choosing All removes that filter from the URL", () => {
    render(<ApplicationFilterBar filters={{ ...ADMIN, agency: "any" }} />);
    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "" } });
    expect(push).toHaveBeenCalledWith("/overseas/admin/applications");
  });

  it("has no Counsellor filter for a counselor, and Clear filters only when one is applied", () => {
    const { rerender } = render(<ApplicationFilterBar filters={{ agency: null, counselor: null, agencies: ADMIN.agencies }} />);
    expect(screen.queryByLabelText("Counsellor")).toBeNull();
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
    rerender(<ApplicationFilterBar filters={{ agency: "org1", counselor: null, agencies: ADMIN.agencies }} />);
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", "/overseas/admin/applications");
  });

  it("announces a refused filter", () => {
    render(<ApplicationFilterBar filters={ADMIN} error="Unknown filter value" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unknown filter value -- showing all applications.");
  });
});
