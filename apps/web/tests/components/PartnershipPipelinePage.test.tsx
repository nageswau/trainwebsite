import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PartnershipPipelineBoard from "@/components/PartnershipPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { Board } from "@/lib/partnershipPipeline";
import PipelinePage from "@/app/partnership/pipeline/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const user = (role: string) => ({ id: "x1", role, full_name: "Rahul", email: "r@x.local", division: "overseas" });
const board = (over: Partial<Board> = {}): Board => ({
  columns: [
    { key: "target", label: "Target", stages: ["target_university", "researching", "contact_identified"], count: 3 },
    { key: "negotiation", label: "Negotiation", stages: ["commercial_discussion", "documents_shared"], count: 0 },
  ],
  lost_count: 1, total: 1, limit: 50, offset: 0,
  items: [{
    id: "u1", university_code: "UNV-000001", name: "ABC University", city: "London", country_name: "United Kingdom", stage: "researching",
    stage_label: "Researching", column: "target", lost: false, primary_manager: { id: "x1", full_name: "Rahul", active: true },
  }],
  ...over,
});
const sp = (q: Record<string, string> = {}) => Promise.resolve(q);
const answer = (role: string, view: Board | Error = board()) =>
  vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return user(role) as never;
    if (view instanceof Error) throw view;
    return view as never;
  });

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(cleanup);

describe("upc-007 Partnership Pipeline page (PS11, PS12)", () => {
  it("defaults a manager to their own universities and keeps the filters in the links", async () => {
    answer("partnership_manager");
    const tree = elements(await PipelinePage({ searchParams: sp() }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/pipeline?manager=me&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("Partnership Manager");
    const props = tree.find((el) => el.type === PartnershipPipelineBoard)!.props as { href: (c: { column?: string | null; offset?: number }) => string };
    expect(props.href({ column: "lost", offset: 0 })).toBe("/partnership/pipeline?column=lost");
    expect(tree.map((el) => text(el)).join(" ")).toContain("All universities");
  });

  it("the All toggle drops the manager filter and is kept in the links", async () => {
    answer("partnership_manager");
    const tree = elements(await PipelinePage({ searchParams: sp({ scope: "all", column: "target", offset: "50" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/pipeline?column=target&limit=50&offset=50");
    const props = tree.find((el) => el.type === PartnershipPipelineBoard)!.props as { href: (c: { offset?: number }) => string; selected: string | null };
    expect(props.href({ offset: 100 })).toBe("/partnership/pipeline?scope=all&column=target&offset=100");
    expect(props.selected).toBe("target");
  });

  it("a head sees every university with no Mine toggle", async () => {
    answer("partnership_head");
    const tree = elements(await PipelinePage({ searchParams: sp() }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/pipeline?limit=50&offset=0");
    expect(tree.map((el) => text(el)).join(" ")).not.toContain("My universities");
  });

  it("a hand-edited filter shows a reset link", async () => {
    answer("partnership_manager", new ApiError("Choose a pipeline column", 422));
    const tree = elements(await PipelinePage({ searchParams: sp({ column: "nope" }) }));
    expect(tree.map((el) => text(el)).join(" ")).toContain("That filter isn't valid.");
  });
});

describe("PartnershipPipelineBoard", () => {
  const href = (c: { column?: string | null; offset?: number }) => `/partnership/pipeline?column=${c.column ?? ""}&offset=${c.offset ?? 0}`;

  it("links each column count and the Lost bucket, and lists the universities", () => {
    render(<PartnershipPipelineBoard view={board()} href={href} selected="target" />);
    const tiles = screen.getByRole("navigation", { name: "Pipeline columns" });
    const target = within(tiles).getByRole("link", { name: /Target/ });
    expect(target).toHaveTextContent("Target3") ;
    expect(target).toHaveAttribute("aria-current", "true");
    expect(within(tiles).getByRole("link", { name: /Lost/ })).toHaveAttribute("href", "/partnership/pipeline?column=lost&offset=0");
    expect(screen.getByRole("heading", { name: "Target" })).toBeInTheDocument();
    const row = screen.getByRole("link", { name: "ABC University" });
    expect(row).toHaveAttribute("href", "/partnership/universities/u1");
    expect(screen.getByText("Researching")).toBeInTheDocument();
  });

  it("says when a column is empty or the page is past the end", () => {
    render(<PartnershipPipelineBoard view={board({ items: [], total: 0 })} href={href} selected="negotiation" />);
    expect(screen.getByRole("status")).toHaveTextContent("No universities in this column.");
    cleanup();
    render(<PartnershipPipelineBoard view={board({ items: [], total: 3, offset: 50 })} href={href} selected={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("This page is past the end of the list.");
  });
});
