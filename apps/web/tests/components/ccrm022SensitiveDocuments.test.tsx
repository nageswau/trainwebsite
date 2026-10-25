import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationChecklistPanel from "@/components/ApplicationChecklistPanel";
import ChecklistTemplateEditor from "@/components/ChecklistTemplateEditor";
import CounselorDocumentReviewPanel from "@/components/CounselorDocumentReviewPanel";
import { sensitivityBadge, STANDARD_STATUSES, typeSensitivity, type ChecklistTemplate } from "@/lib/documentChecklists";

// ccrm-022 (DEC-SCOPE-263): sensitivity classes -- the type rule mirrored from the server, the template editor's select, and the
// "Sensitive" badges on the counselor's document queue and the application checklist.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });

describe("sensitivity helpers", () => {
  it("classes a type by whole words, as the server does", () => {
    expect(typeSensitivity("Passport")).toBe("identity");
    expect(typeSensitivity("Financial documents")).toBe("financial");
    expect(typeSensitivity("Other", "Bank statement")).toBe("financial");
    expect(typeSensitivity("Bankruptcy-free")).toBe("standard");
    expect(typeSensitivity("Transcripts")).toBe("standard");
  });

  it("badges only identity and financial", () => {
    expect(sensitivityBadge("identity")).toBe("Sensitive · Identity");
    expect(sensitivityBadge("financial")).toBe("Sensitive · Financial");
    expect(sensitivityBadge("standard")).toBeNull();
    expect(sensitivityBadge(undefined)).toBeNull();
  });
});

describe("ChecklistTemplateEditor sensitivity", () => {
  const template = {
    id: "t1", name: "UK Masters", kind: "admission", country_id: "c1", country_name: "United Kingdom", university_id: null, university_name: null,
    course_level: null, intake: null, gate_mode: "block", version: 2, active: true, updated_at: "2026-10-23T10:00:00Z", notes: null,
    items: [{ id: "i1", position: 1, document_type: "Transcripts", label: null, required: true, allowed_statuses: [...STANDARD_STATUSES], notes: null, sensitivity: "financial" }],
  } as ChecklistTemplate;  // prettier-ignore

  it("shows the stored class, follows a type change and saves the chosen class", async () => {
    const fetchMock = vi.fn(() => json(template));
    vi.stubGlobal("fetch", fetchMock);
    render(<ChecklistTemplateEditor template={template} onSaved={vi.fn()} onCancel={vi.fn()} />);
    const first = screen.getByRole("listitem", { name: "Document 1" });
    const select = within(first).getByLabelText("Sensitivity") as HTMLSelectElement;
    expect(select.value).toBe("financial");
    expect(select).toHaveAccessibleDescription(/hidden from university representatives/);
    fireEvent.change(within(first).getByLabelText("Document type"), { target: { value: "Passport" } });
    expect(select.value).toBe("identity");
    fireEvent.change(select, { target: { value: "financial" } });
    fireEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect((within(screen.getByRole("listitem", { name: "Document 2" })).getByLabelText("Sensitivity") as HTMLSelectElement).value).toBe("identity");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("button", { name: "Save changes" });
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body.items.map((i: { sensitivity: string }) => i.sensitivity)).toEqual(["financial", "identity"]);
  });
});

describe("Sensitive badges", () => {
  it("marks identity and financial documents on the counselor's queue", async () => {
    const rows = [
      { id: "d1", student: "Asha Rao", document: "Passport", status: "pending", sensitivity: "identity" },
      { id: "d2", student: "Ravi Iyer", document: "Transcripts", status: "pending", sensitivity: "standard" },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ rows }), { status: 200 })));
    render(<CounselorDocumentReviewPanel />);
    const passport = (await screen.findByText("Passport")).closest(".card") as HTMLElement;
    expect(within(passport).getByText("Sensitive · Identity")).toBeInTheDocument();
    const transcript = screen.getByText("Transcripts").closest(".card") as HTMLElement;
    expect(within(transcript).queryByText(/Sensitive/)).toBeNull();
  });

  it("marks a sensitive checklist item", async () => {
    const item = (over: Record<string, unknown>) => ({
      id: "i1", position: 1, document_type: "Passport", label: null, name: "Passport", required: true, notes: null, allowed_statuses: [], mark: null,
      status: "missing", status_label: "Missing", removable: false, documents: [], sensitivity: "identity", ...over,
    });  // prettier-ignore
    const checklist = {
      template_id: null, template_version: null, gate_mode: "warn", documents_completed_on: null,
      summary: { required_total: 2, required_complete: 0, optional_total: 0, optional_complete: 0, ready: false, missing: [] },
      items: [item({}), item({ id: "i2", document_type: "CV", name: "CV", sensitivity: "standard" })],
    };  // prettier-ignore
    vi.stubGlobal("fetch", vi.fn(() => json({ checklist, template: null, documents: [] })));
    render(<ApplicationChecklistPanel applicationId="a1" readOnly />);
    expect(await screen.findByText("Sensitive · Identity")).toBeInTheDocument();
    expect(screen.getAllByText(/Sensitive ·/)).toHaveLength(1);
  });
});
