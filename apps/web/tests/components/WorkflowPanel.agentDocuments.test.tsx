import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const agent = (memberRole: "master" | "staff", canVerify: boolean) =>
  ({ id: "u1", email: "a@example.local", full_name: "A", role: "agent", division: "overseas", profile: {}, agent_member_role: memberRole, agent_permissions: { can_verify_documents: canVerify, can_view_reports: false } }) as unknown as User;

function stub() {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.startsWith("/api/v1/portal/overseas/agent/documents") ? json({ rows: [{ id: "d1", student: "Asha Rao", document: "Passport", status: "pending" }] }) : json([]))));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel agent Documents (AGN-003)", () => {
  it("shows no review queue without the Verify permission", () => {
    stub();
    render(<WorkflowPanel user={agent("staff", false)} section="documents" />);
    expect(screen.queryByRole("heading", { name: "Document Verification" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Upload document" })).toBeInTheDocument();
  });

  it("gives staff with Verify a Mark verified action only", async () => {
    stub();
    render(<WorkflowPanel user={agent("staff", true)} section="documents" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(screen.getByRole("button", { name: "Mark verified" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Decision")).toBeNull();
  });

  it("gives a Master all three decisions", async () => {
    stub();
    render(<WorkflowPanel user={agent("master", true)} section="documents" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect([...(screen.getByLabelText("Decision") as HTMLSelectElement).options].map((o) => o.value)).toEqual(["verified", "rejected", "changes_required"]);
  });
});
