import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const agent = (memberRole: "master" | "staff", canVerify: boolean) =>
  ({ id: "u1", email: "a@example.local", full_name: "A", role: "agent", division: "overseas", profile: {}, agent_member_role: memberRole, agent_permissions: { can_verify_documents: canVerify, can_view_reports: false } }) as unknown as User;
const student = { id: "s1", email: "s@example.local", full_name: "S", role: "overseas_student", division: "overseas", profile: {} } as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// AGN-009 (DEC-SCOPE-051): the agent Documents page is AgentDocumentsSection (PortalPage). The generic upload form and the AGN-003
// review queue it replaces are no longer rendered for agents; a student's Documents page is unchanged.
describe("WorkflowPanel Documents", () => {
  it.each([
    ["master", true],
    ["staff", true],
    ["staff", false],
  ] as const)("renders no generic upload or review queue for an agency %s (verify=%s)", (role, canVerify) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json([]))));
    render(<WorkflowPanel user={agent(role, canVerify)} section="documents" />);
    expect(screen.queryByRole("heading", { name: "Upload document" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Document Verification" })).toBeNull();
  });

  it("keeps a student's upload form", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json([]))));
    render(<WorkflowPanel user={student} section="documents" />);
    expect(screen.getByRole("heading", { name: "Upload document" })).toBeInTheDocument();
  });
});
