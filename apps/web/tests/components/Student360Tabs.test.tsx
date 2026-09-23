import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/school/coordinator/students/s1/360" }));

import Student360Tabs, { type TabSummary } from "@/components/Student360Tabs";

afterEach(() => {
  cleanup();
  replace.mockReset();
});

const TABS: TabSummary[] = [
  { key: "overview", label: "Overview", status: "has_data", count: null },
  { key: "skills", label: "Skills", status: "has_data", count: 3 },
  { key: "attendance", label: "Attendance", status: "restricted", count: null },
  { key: "documents", label: "Documents", status: "empty", count: 0 },
];

function setup(initial: TabSummary["key"] = "overview") {
  return render(
    <Student360Tabs tabs={TABS} initialTab={initial}>
      {TABS.map((t) => <p key={t.key}>{t.label} panel</p>)}
    </Student360Tabs>,
  );
}

const tabs = () => screen.getAllByRole("tab");

describe("Student360Tabs", () => {
  it("renders the ARIA tabs pattern with only the selected tab in the tab order", () => {
    setup();
    expect(screen.getByRole("tablist", { name: /student record sections/i })).toBeInTheDocument();
    expect(tabs()).toHaveLength(4);
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[0]).toHaveAttribute("tabindex", "0");
    expect(tabs()[1]).toHaveAttribute("aria-selected", "false");
    expect(tabs()[1]).toHaveAttribute("tabindex", "-1");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", tabs()[0].id);
    expect(tabs()[0]).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("tabindex", "0");
    expect(panel).toHaveTextContent("Overview panel");
    expect(screen.queryByText("Skills panel")).not.toBeInTheDocument();
  });

  it("states count, empty and restricted in the accessible name, not by colour alone", () => {
    setup();
    expect(screen.getByRole("tab", { name: /skills.*3 records/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /documents.*no records yet/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /attendance.*not available for your role/i })).toBeInTheDocument();
  });

  it("moves with arrow keys in both axes, wraps, and supports Home/End, moving focus with the selection", () => {
    setup();
    fireEvent.keyDown(tabs()[0], { key: "ArrowRight" });
    expect(tabs()[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs()[1]);
    fireEvent.keyDown(tabs()[1], { key: "ArrowDown" });
    expect(tabs()[2]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs()[2], { key: "ArrowUp" });
    expect(tabs()[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs()[1], { key: "ArrowLeft" });
    fireEvent.keyDown(tabs()[0], { key: "ArrowLeft" });
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs()[3], { key: "ArrowRight" });
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs()[0], { key: "End" });
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs()[3], { key: "Home" });
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(tabs()[0]);
  });

  it("ignores other keys", () => {
    setup();
    fireEvent.keyDown(tabs()[0], { key: "a" });
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps the selection in ?tab= without scrolling, and shows that panel", () => {
    setup();
    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    expect(replace).toHaveBeenCalledWith("/school/coordinator/students/s1/360?tab=skills", { scroll: false });
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Skills panel");
  });

  it("starts on the initial tab", () => {
    setup("documents");
    expect(screen.getByRole("tab", { name: /documents/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Documents panel");
  });
});
