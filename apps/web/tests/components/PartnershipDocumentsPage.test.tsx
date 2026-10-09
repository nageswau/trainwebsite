import { beforeEach, describe, expect, it, vi } from "vitest";

import { serverApi } from "@/lib/api";
import DocumentsPage from "@/app/partnership/documents/page";
import { documentListQuery, documentPageHref } from "@/lib/universityDocuments";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const person = { id: "p1", full_name: "Rahul Mehta", active: true };
const doc = {
  id: "d1", university: { id: "u1", name: "ABC University", university_code: "UNV-000001" }, kind: "fee_structure", title: "Fees 2026",
  shareable: true, current_version: 1,
  versions: [{ version: 1, file_name: "fees.pdf", content_type: "application/pdf", size_bytes: 2048, uploaded_by: person, uploaded_at: "2026-10-09T05:00:00Z" }],
  created_at: "", updated_at: "2026-10-09T05:00:00Z",
};
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });

function stub(result: unknown) {
  vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? ({ role: "partnership_manager", full_name: "Rahul" } as never) : (result as never)));
}

beforeEach(() => vi.mocked(serverApi).mockReset());

describe("upc-026 documents menu page", () => {
  it("passes only the known filters and the page to the API", async () => {
    stub(page([doc]));
    await DocumentsPage({ searchParams: Promise.resolve({ kind: "fee_structure", q: " ABC ", offset: "50" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/partnership/documents?kind=fee_structure&q=ABC&limit=50&offset=50");
    expect(documentListQuery({ q: "" }, 20, 0)).toBe("limit=20&offset=0");
    expect(documentPageHref({ kind: "mou" }, 0)).toBe("/partnership/documents?kind=mou");
  });

  it("lists each document with its university link, kind and download", async () => {
    stub(page([doc]));
    const view = await DocumentsPage({ searchParams: Promise.resolve({}) });
    const tree = elements(view);
    const links = tree.filter((el) => el.type === "a" || (typeof el.props.href === "string" && el.props.href));
    expect(links.some((el) => el.props.href === "/partnership/universities/u1")).toBe(true);
    expect(links.some((el) => el.props.href === "/api/v1/partnership/universities/u1/documents/d1/file")).toBe(true);
    expect(text(view)).toContain("Fee structure");
  });

  it("shows the empty and the filtered-empty states", async () => {
    stub(page([]));
    expect(text(await DocumentsPage({ searchParams: Promise.resolve({}) }))).toContain("No documents uploaded yet.");
    stub(page([]));
    expect(text(await DocumentsPage({ searchParams: Promise.resolve({ kind: "mou" }) }))).toContain("No documents match these filters.");
  });

  it("offers paging when there are more documents", async () => {
    stub(page([doc], 120));
    const tree = elements(await DocumentsPage({ searchParams: Promise.resolve({ kind: "mou" }) }));
    expect(tree.some((el) => el.props.href === "/partnership/documents?kind=mou&offset=1")).toBe(true);
  });
});
