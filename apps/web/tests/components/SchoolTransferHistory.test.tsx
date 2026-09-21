import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTransferHistory, { loadTransferHistory, type TransferHistoryEntry } from "@/components/SchoolTransferHistory";
import { serverApi } from "@/lib/api";

// ENH-005 -- read-only transfer history (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §5.2, §7.1).
// `serverApi` reads next/headers cookies, so it is mocked.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const entry: TransferHistoryEntry = { id: "t1", decided_at: "2026-09-21T10:00:00Z", from_school: { id: "a", name: "Sunrise School" }, to_school: { id: "b", name: "Lakeview School" } };

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolTransferHistory", () => {
  it("renders nothing for a student who has never transferred (no empty card on every page)", () => {
    const { container } = render(<SchoolTransferHistory history={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("states a transfer in text: a badge, the move, and the date", () => {
    render(<SchoolTransferHistory history={[entry]} />);
    expect(screen.getByRole("heading", { name: "Transfer history" })).toBeTruthy();
    expect(screen.getByText("Transferred")).toBeTruthy();
    expect(screen.getByText("Moved from Sunrise School to Lakeview School")).toBeTruthy();
    // ICU renders September as "Sep" or "Sept" depending on the Node/browser version.
    expect(screen.getByText(/21 Sep\w* 2026/)).toBeTruthy();
  });

  it("keeps the failure visible: an unavailable line, not nothing", () => {
    render(<SchoolTransferHistory history={null} />);
    expect(screen.getByText("Transfer history is unavailable right now.")).toBeTruthy();
  });
});

describe("loadTransferHistory", () => {
  it("reads the coordinator/parent endpoint and returns the entries", async () => {
    vi.mocked(serverApi).mockResolvedValue({ student: { id: "s1", full_name: "Aarav" }, history: [entry] });
    await expect(loadTransferHistory("s1")).resolves.toEqual([entry]);
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/students/s1/transfer-history");
  });

  it("returns null (unavailable) when the read fails", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("500"));
    await expect(loadTransferHistory("s1")).resolves.toBeNull();
  });
});
