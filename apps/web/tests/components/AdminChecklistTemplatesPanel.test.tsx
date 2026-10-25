import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminChecklistTemplatesPanel from "@/components/AdminChecklistTemplatesPanel";
import ChecklistTemplateEditor from "@/components/ChecklistTemplateEditor";
import { scopeText, STANDARD_STATUSES, type ChecklistTemplate } from "@/lib/documentChecklists";

// ccrm-018 (DEC-SCOPE-248): the Overseas Admin's checklist templates -- list states, filters, opening the editor and saving.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const URL = "/api/v1/overseas-admin/checklists";
const summary = (over: Record<string, unknown> = {}) => ({
  id: "t1", name: "UK Masters", kind: "admission", country_id: "c1", country_name: "United Kingdom", university_id: null, university_name: null,
  course_level: "PG", intake: null, gate_mode: "block", version: 2, active: true, item_count: 3, updated_at: "2026-10-23T10:00:00Z", ...over,
});
const template = (over: Record<string, unknown> = {}) => ({
  ...summary(), notes: null,
  items: [
    { id: "i1", position: 1, document_type: "Passport", label: null, required: true, allowed_statuses: [...STANDARD_STATUSES], notes: null, sensitivity: "identity" },
    { id: "i2", position: 2, document_type: "CV", label: null, required: false, allowed_statuses: ["draft", "review", "approved"], notes: "Latest", sensitivity: "standard" },
  ],
  ...over,
});

describe("documentChecklists helpers", () => {
  it("describes a scope with the unset parts as 'any'", () => {
    expect(scopeText({ country_name: "United Kingdom", university_name: null, course_level: "PG", intake: null })).toBe("United Kingdom · Any university · PG · Any intake");
  });
});

describe("AdminChecklistTemplatesPanel", () => {
  it("shows loading, then the empty state that says nothing applies universally", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ items: [] })));
    render(<AdminChecklistTemplatesPanel />);
    expect(screen.getByText("Loading checklist templates…")).toBeInTheDocument();
    expect(await screen.findByText(/No templates here yet/)).toBeInTheDocument();
  });

  it("shows a load failure with a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "x" }, false, 500)).mockReturnValue(json({ items: [summary()] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminChecklistTemplatesPanel />);
    expect(await screen.findByText("Unable to load checklist templates.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("UK Masters")).toBeInTheDocument();
  });

  it("lists templates with scope, gate and version, and refetches on a filter change", async () => {
    const fetchMock = vi.fn(() => json({ items: [summary(), summary({ id: "t2", name: "UK visa", kind: "visa", active: false, gate_mode: "warn" })] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminChecklistTemplatesPanel />);
    expect(await screen.findByText("UK Masters")).toBeInTheDocument();
    expect(screen.getAllByText("United Kingdom · Any university · PG · Any intake")).toHaveLength(2);
    expect(screen.getByText("Warn (override with a reason)")).toBeInTheDocument();
    expect(screen.getByText("Inactive", { selector: ".badge" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(`${URL}?status=active`);
    fireEvent.change(screen.getByLabelText("Checklist for"), { target: { value: "visa" } });
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(`${URL}?status=active&kind=visa`));
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(`${URL}?status=all&kind=visa`));
  });

  it("opens the full template for editing and saves it with the loaded version", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PUT") return json(template({ version: 3, gate_mode: "warn" }));
      if (url === `${URL}/t1`) return json(template());
      return json({ items: [summary()] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminChecklistTemplatesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit UK Masters" }));
    const form = await screen.findByRole("form", { name: "Edit UK Masters" });
    expect(within(form).getAllByRole("listitem")).toHaveLength(2);
    fireEvent.click(within(form).getByLabelText("Warn (override with a reason)"));
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved UK Masters (version 3).")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(put?.[0]).toBe(`${URL}/t1`);
    const body = JSON.parse(String(put?.[1]?.body));
    expect(body).toMatchObject({ version: 2, active: true, gate_mode: "warn", course_level: "PG", university_id: null });
    expect(body.items.map((i: { document_type: string }) => i.document_type)).toEqual(["Passport", "CV"]);
    expect(body.items[1].allowed_statuses).toEqual(["draft", "review", "approved"]);
  });

  it("shows why a template could not be opened", async () => {
    const fetchMock = vi.fn((url: string) => (url === `${URL}/t1` ? json({ detail: "Checklist template not found" }, false, 404) : json({ items: [summary()] })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminChecklistTemplatesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit UK Masters" }));
    expect(await screen.findByText("Checklist template not found")).toBeInTheDocument();
  });
});

describe("ChecklistTemplateEditor", () => {
  it("adds, reorders and removes documents, and an 'Other' document needs a name", () => {
    render(<ChecklistTemplateEditor template={template() as ChecklistTemplate} onSaved={vi.fn()} onCancel={vi.fn()} />);
    const form = screen.getByRole("form", { name: "Edit UK Masters" });
    fireEvent.click(within(form).getByRole("button", { name: "Add document" }));
    expect(within(form).getAllByRole("listitem")).toHaveLength(3);
    fireEvent.click(within(form).getByRole("button", { name: "Move document 2 up" }));
    const first = within(form).getByRole("listitem", { name: "Document 1" });
    expect((within(first).getByLabelText("Document type") as HTMLSelectElement).value).toBe("CV");
    fireEvent.click(within(form).getByRole("button", { name: "Remove document 3" }));
    expect(within(form).getAllByRole("listitem")).toHaveLength(2);
    fireEvent.change(within(first).getByLabelText("Document type"), { target: { value: "Other" } });
    expect(within(first).getByLabelText("Document name")).toBeRequired();
  });

  it("keeps focus on the moved document, even when it reaches the top (QA-01)", async () => {
    render(<ChecklistTemplateEditor template={template() as ChecklistTemplate} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Move document 2 up" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Move document 1 down" })));
  });

  it("keeps the entry and shows the server's 409", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "An active template already covers this kind and scope; edit that one or deactivate it first" }, false, 409)));
    const onSaved = vi.fn();
    render(<ChecklistTemplateEditor template={template() as ChecklistTemplate} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An active template already covers this kind and scope");
    expect(screen.getByLabelText("Name")).toHaveValue("Renamed");
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("cancels on Escape", () => {
    const onCancel = vi.fn();
    render(<ChecklistTemplateEditor template={null} onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Create template" })).toBeDisabled(); // no country yet
  });
});
