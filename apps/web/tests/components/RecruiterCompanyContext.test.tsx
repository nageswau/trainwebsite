import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyBusiness from "@/components/RecruiterCompanyBusiness";
import RecruiterCompanyDocuments from "@/components/RecruiterCompanyDocuments";
import { contextBody, contextOf, splitList } from "@/lib/recruiterCompanies";
import type { Company } from "@/lib/recruiterCompanies";

// pob-003 (DEC-SCOPE-406): the company's business context and its document store.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(handler(call));
  }));
  return calls;
}

const context = {
  products_services: "Payroll software",
  departments_hiring: ["Engineering", "Sales"],
  hiring_locations: ["Pune"],
  target_roles: ["Java Developer"],
  branch_locations: [{ city: "Pune", state: "Maharashtra", country: "India" }],
  skill_demand: [{ id: "s1", name: "Java", active: true }, { id: "s2", name: "COBOL", active: false }],
};
const company = { id: "c1", permissions: { can_edit: true }, ...context } as unknown as Company;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("splits a comma list, trimming and dropping blanks", () => {
    expect(splitList(" Engineering, ,Sales ,")).toEqual(["Engineering", "Sales"]);
    expect(splitList("")).toEqual([]);
  });

  it("sends only the changed context fields", () => {
    const original = contextOf(company);
    expect(contextBody(original, original)).toEqual({});
    const next = { ...original, departments: "Engineering, QA", branches: [...original.branches, { city: "Austin", state: "", country: "USA" }] };
    expect(contextBody(next, original)).toEqual({
      departments_hiring: ["Engineering", "QA"],
      branch_locations: [{ city: "Pune", state: "Maharashtra", country: "India" }, { city: "Austin", state: null, country: "USA" }],
    });
  });
});

describe("RecruiterCompanyBusiness", () => {
  it("shows the context, with an inactive skill marked and empty values as None recorded", () => {
    render(<RecruiterCompanyBusiness company={{ ...company, target_roles: [] }} onSaved={() => undefined} />);
    const section = screen.getByRole("region", { name: "Business context" });
    expect(within(section).getByText("Engineering, Sales")).toBeTruthy();
    expect(within(section).getByText("Pune, Maharashtra, India")).toBeTruthy();
    expect(within(section).getByText("Java, COBOL (inactive)")).toBeTruthy();
    expect(within(section).getByText("None recorded")).toBeTruthy();
  });

  it("offers Edit only with can_edit", () => {
    render(<RecruiterCompanyBusiness company={{ ...company, permissions: { ...company.permissions, can_edit: false } }} onSaved={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Edit business context" })).toBeNull();
  });

  it("adds a branch, saves only the changes and hands back the saved company", async () => {
    const saved = vi.fn();
    const calls = serve(() => res({ company: { ...company, target_roles: ["Tester"] } }));
    render(<RecruiterCompanyBusiness company={company} onSaved={saved} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit business context" }));
    fireEvent.change(screen.getByLabelText("Target roles"), { target: { value: "Tester" } });
    fireEvent.click(screen.getByRole("button", { name: "Add branch" }));
    fireEvent.change(screen.getByLabelText("Branch 2 City"), { target: { value: "Austin" } });
    fireEvent.click(screen.getByRole("button", { name: "Save business context" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    const write = calls.find((c) => c.init?.method === "PATCH")!;
    expect(write.url).toBe("/api/v1/recruiter/companies/c1");
    expect(JSON.parse(String(write.init!.body))).toEqual({
      target_roles: ["Tester"],
      branch_locations: [{ city: "Pune", state: "Maharashtra", country: "India" }, { city: "Austin", state: null, country: null }],
    });
  });

  it("removes a skill and a branch", async () => {
    const calls = serve(() => res({ company }));
    render(<RecruiterCompanyBusiness company={company} onSaved={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit business context" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove skill Java" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove branch 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Save business context" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body))).toEqual({ skill_demand_ids: ["s2"], branch_locations: [] });
  });

  it("refuses a branch without a city before calling the server, and shows a server error", async () => {
    const calls = serve(() => res({ detail: "Add at most 20 departments hiring" }, 422));
    render(<RecruiterCompanyBusiness company={company} onSaved={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit business context" }));
    fireEvent.click(screen.getByRole("button", { name: "Add branch" }));
    fireEvent.click(screen.getByRole("button", { name: "Save business context" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Enter a city for every branch");
    expect(calls.length).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Remove branch 2" }));
    fireEvent.change(screen.getByLabelText("Departments hiring"), { target: { value: "A, B" } });
    fireEvent.click(screen.getByRole("button", { name: "Save business context" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Add at most 20 departments hiring");
  });

  it("says when nothing changed", async () => {
    const saved = vi.fn();
    const calls = serve(() => res({ company }));
    render(<RecruiterCompanyBusiness company={company} onSaved={saved} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit business context" }));
    fireEvent.click(screen.getByRole("button", { name: "Save business context" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(company, false));
    expect(calls.length).toBe(0);
  });
});

const uploader = { id: "u1", full_name: "Priya Recruiter", active: true };
const doc = (over: Record<string, unknown> = {}) => ({
  id: "d1", kind: "company_profile", name: "profile.pdf", content_type: "application/pdf", size_bytes: 2048, meeting: null, uploaded_by: uploader,
  created_at: "2026-11-05T10:00:00Z", can_download: true, ...over,
});
const docPage = (items: unknown[], over: Record<string, unknown> = {}) => ({ items, total: items.length, limit: 50, offset: 0, can_upload: true, can_upload_agreement: true, ...over });

describe("RecruiterCompanyDocuments", () => {
  it("lists documents with their type, uploader and a download link", async () => {
    serve((c) => (c.url.includes("/meetings") ? res({ items: [], total: 0 }) : res(docPage([doc(), doc({ id: "d2", kind: "recruitment_agreement", name: "msa.pdf", can_download: false, meeting: { id: "m1", code: "MTG-000001", starts_at: "2026-11-01T10:00:00Z" } })]))));
    render(<RecruiterCompanyDocuments companyId="c1" />);
    const table = await screen.findByRole("region", { name: "Company documents" });
    expect(within(table).getByText("Company profile")).toBeTruthy();
    expect(within(table).getByText("Recruitment agreement")).toBeTruthy();
    expect(within(table).getByText("MTG-000001")).toBeTruthy();
    expect(within(table).getByRole("link", { name: "Download profile.pdf" }).getAttribute("href")).toBe("/api/v1/recruiter/companies/documents/d1/download");
    expect(within(table).queryByRole("link", { name: "Download msa.pdf" })).toBeNull();
    expect(within(table).getByText("Needs commercial access")).toBeTruthy();
  });

  it("shows the empty state and hides the upload form without can_upload", async () => {
    serve(() => res(docPage([], { can_upload: false, can_upload_agreement: false })));
    render(<RecruiterCompanyDocuments companyId="c1" />);
    expect(await screen.findByText("No documents yet.")).toBeTruthy();
    expect(screen.queryByLabelText("Document type")).toBeNull();
  });

  it("offers the agreement type only with can_upload_agreement", async () => {
    serve((c) => (c.url.includes("/meetings") ? res({ items: [], total: 0 }) : res(docPage([], { can_upload_agreement: false }))));
    render(<RecruiterCompanyDocuments companyId="c1" />);
    const kind = (await screen.findByLabelText("Document type")) as HTMLSelectElement;
    expect([...kind.options].map((o) => o.value)).not.toContain("recruitment_agreement");
    expect([...kind.options].map((o) => o.value)).toContain("meeting_notes");
  });

  it("shows a load error with Retry", async () => {
    let fail = true;
    serve((c) => (c.url.includes("/meetings") ? res({ items: [], total: 0 }) : fail ? res({ detail: "boom" }, 500) : res(docPage([]))));
    render(<RecruiterCompanyDocuments companyId="c1" />);
    expect(await screen.findByText("Unable to load documents.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry documents" }));
    expect(await screen.findByText("No documents yet.")).toBeTruthy();
  });

  it("uploads the chosen file with its type and meeting, then lists it", async () => {
    let uploaded = false;
    const calls = serve((c) => {
      if (c.url.includes("/meetings")) return res({ items: [{ id: "m1", code: "MTG-000001", meeting_type: "contract_discussion", starts_at: "2026-11-01T10:00:00Z" }], total: 1 });
      if (c.init?.method === "POST") {
        uploaded = true;
        return res({ document: doc({ kind: "meeting_notes", name: "notes.pdf" }) }, 201);
      }
      return res(docPage(uploaded ? [doc({ kind: "meeting_notes", name: "notes.pdf" })] : []));
    });
    render(<RecruiterCompanyDocuments companyId="c1" />);
    fireEvent.change(await screen.findByLabelText("Document type"), { target: { value: "meeting_notes" } });
    await screen.findByRole("option", { name: /MTG-000001/ });
    fireEvent.change(screen.getByLabelText("Linked meeting (optional)"), { target: { value: "m1" } });
    const file = new File(["%PDF-1.4"], "notes.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/^File/), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText("Document uploaded.")).toBeTruthy();
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(post.url).toBe("/api/v1/recruiter/companies/c1/documents");
    const body = post.init!.body as FormData;
    expect(body.get("kind")).toBe("meeting_notes");
    expect(body.get("meeting_id")).toBe("m1");
    expect((body.get("file") as File).name).toBe("notes.pdf");
  });

  it("checks the file before calling the server and shows a server refusal", async () => {
    const calls = serve((c) => (c.init?.method === "POST" ? res({ detail: "Too many uploads. Try again later." }, 429) : c.url.includes("/meetings") ? res({ items: [], total: 0 }) : res(docPage([]))));
    render(<RecruiterCompanyDocuments companyId="c1" />);
    await screen.findByLabelText("Document type");
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Choose a file");
    fireEvent.change(screen.getByLabelText(/^File/), { target: { files: [new File(["x"], "a.docx", { type: "application/msword" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Upload a PDF, JPEG or PNG file");
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
    fireEvent.change(screen.getByLabelText(/^File/), { target: { files: [new File(["%PDF"], "a.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Too many uploads");
  });
});
