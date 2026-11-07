import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyImport from "@/components/RecruiterCompanyImport";
import RecruiterCompanyMerge, { RecruiterContactMerge } from "@/components/RecruiterCompanyMerge";
import { previewCounts, reportCounts } from "@/lib/recruiterCompanyImport";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

type Reply = { status?: number; body: unknown };
function mockFetch(handler: (url: string, init?: RequestInit) => Reply) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = handler(String(url), init);
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const PAGE = { items: [], total: 0, limit: 50, offset: 0 };
const ROW = { contact: null, company: null, company_outcome: "new", contact_outcome: "new", same_as_row: null, company_name: "Acme", contact_name: "Asha" };
const PREVIEW = {
  total_rows: 2, new_count: 1, created_count: 0, matched_count: 0, error_count: 1, companies_created: 0, contacts_created: 0,
  rows: [{ ...ROW, row_number: 2, status: "new", reason: null }, { ...ROW, row_number: 3, status: "error", company_outcome: null, contact_outcome: null, reason: "Enter a valid email address" }],
};
const REPORT = {
  id: "b1", file_name: "c.csv", uploaded_by: { id: "u", full_name: "U" }, total_rows: 2, created_count: 1, matched_count: 0, error_count: 1, companies_created: 1, contacts_created: 1, created_at: "2026-11-06T00:00:00Z", replayed: false,
  rows: [{ row_number: 2, status: "created", company: { id: "c1", code: "CMP-1", name: "Acme", in_scope: true }, contact: { id: "p1", name: "Asha" }, company_outcome: "created", contact_outcome: "created", reason: null }],
};

afterEach(cleanup);

function chooseFile(name = "companies.csv") {
  fireEvent.change(screen.getByLabelText("Filled-in companies file"), { target: { files: [new File(["company_name\nAcme"], name, { type: "text/csv" })] } });
}

describe("RecruiterCompanyImport", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    push.mockReset();
  });

  it("refuses a wrong file type without calling the server", async () => {
    const fetchMock = mockFetch(() => ({ body: PAGE }));
    render(<RecruiterCompanyImport />);
    chooseFile("companies.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a .csv or .xlsx file.");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it("checks, shows each row's reason, imports with a key and shows the report", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url.endsWith("/preview")) return { body: PREVIEW };
      if (init?.method === "POST") return { status: 201, body: REPORT };
      return { body: PAGE };
    });
    render(<RecruiterCompanyImport />);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import 1 new row" }));
    expect(await screen.findByRole("heading", { name: "Import result" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CMP-1" })).toHaveAttribute("href", "/recruiter/companies/c1");
    const commit = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/company-imports") && init?.method === "POST");
    expect((commit?.[1]?.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });

  it("shows the server's refusal", async () => {
    mockFetch((url) => (url.endsWith("/preview") ? { status: 422, body: { detail: "Unknown column secret" } } : { body: PAGE }));
    render(<RecruiterCompanyImport />);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown column secret");
  });

  it("words the counts", () => {
    expect(reportCounts({ companies_created: 1, contacts_created: 2, matched_count: 0, error_count: 1 })).toBe("1 company and 2 contacts added, 0 rows already here, 1 error");
    expect(previewCounts({ total_rows: 1, new_count: 1, matched_count: 0, error_count: 0, rows: [] })).toContain("1 row adds something new");
  });
});

const SIDE = (code: string, city: string | null) => ({ id: code, code, name: `${code} Name`, assigned_recruiter: null, values: { city, website: null } });

describe("RecruiterCompanyMerge", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    push.mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("asks for a code first", () => {
    render(<RecruiterCompanyMerge survivorId="s" />);
    expect(screen.getByRole("heading", { name: "Merge a duplicate company" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Merge/ })).toBeNull();
  });

  it("sends the chosen field and leads back to the survivor", async () => {
    const fetchMock = mockFetch((_url, init) =>
      init?.method === "POST" ? { body: { id: "S" } } : { body: { survivor: SIDE("S", "Pune"), victim: SIDE("V", "Goa"), fields: ["city", "website"], moved: { calls: 2, contacts: 0 }, blocked: [] } },
    );
    render(<RecruiterCompanyMerge survivorId="S" victimCode="V" />);
    fireEvent.click(await screen.findByRole("radio", { name: "Keep Goa for City" }));
    expect(screen.getByText("Moves to S: calls: 2.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Merge V" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/companies/S?merged=V"));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ victim_code: "V", use_victim: ["city"] });
  });

  it("warns when the duplicate's recruiter is someone else, and not otherwise", async () => {
    const side = (code: string, assigned_recruiter: string | null) => ({ ...SIDE(code, null), assigned_recruiter });
    const reply = (a: string | null, b: string | null) => mockFetch(() => ({ body: { survivor: side("S", a), victim: side("V", b), fields: [], moved: {}, blocked: [] } }));
    reply("Kiran", "Ravi");
    const { unmount } = render(<RecruiterCompanyMerge survivorId="S" victimCode="V" />);
    expect(await screen.findByText(/Ravi loses access to what moves/)).toBeInTheDocument();
    unmount();
    reply("Kiran", "Kiran");
    render(<RecruiterCompanyMerge survivorId="S" victimCode="V" />);
    await screen.findByRole("button", { name: "Merge V" });
    expect(screen.queryByText(/loses access/)).toBeNull();
  });

  it("disables Merge when something blocks it, and shows a missing company", async () => {
    mockFetch(() => ({ body: { survivor: SIDE("S", null), victim: SIDE("V", null), fields: [], moved: {}, blocked: ["Both companies have a contract in effect"] } }));
    const { unmount } = render(<RecruiterCompanyMerge survivorId="S" victimCode="V" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("contract in effect");
    expect(screen.getByRole("button", { name: "Merge V" })).toBeDisabled();
    unmount();
    mockFetch(() => ({ status: 404, body: { detail: "Company not found" } }));
    render(<RecruiterCompanyMerge survivorId="S" victimCode="X" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Company not found");
  });
});

describe("RecruiterContactMerge", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    push.mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("warns that Do not contact carries over, then merges", async () => {
    const side = (id: string, status: string) => ({ id, name: id, status, is_primary: false, is_decision_maker: false, active: true, values: { name: id } });
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "POST") return { body: {} };
      if (url.includes("/contacts/p1/merge")) return { body: { company: { id: "c", code: "CMP", name: "Acme" }, survivor: side("p1", "replied"), victim: side("p2", "do_not_contact"), fields: ["name"], moved: {} } };
      return { body: { items: [{ id: "p1", name: "p1", mobile: null, email: null }, { id: "p2", name: "p2", mobile: "98", email: null }], can_edit: false } };
    });
    render(<RecruiterContactMerge companyId="c" survivorId="p1" />);
    fireEvent.change(await screen.findByLabelText("Duplicate contact"), { target: { value: "p2" } });
    expect(await screen.findByText(/becomes Do not contact too/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Merge contact" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/companies/c?merged=contact"));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body))).toEqual({ victim_id: "p2", use_victim: [] });
  });

  it("says so when there is nobody else", async () => {
    mockFetch(() => ({ body: { items: [{ id: "p1", name: "p1" }], can_edit: false } }));
    render(<RecruiterContactMerge companyId="c" survivorId="p1" />);
    expect(await screen.findByText("This company has no other contact to merge.")).toBeInTheDocument();
  });
});
