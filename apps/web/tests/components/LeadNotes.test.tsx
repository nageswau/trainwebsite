import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadNotes from "@/components/LeadNotes";
import type { LeadNote } from "@/lib/leadNotes";

// ccrm-002 (DEC-SCOPE-242): the notes panel -- the full text newest first, add with a trimmed body, the 4000 limit and the failure path.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const note = (id: string, body: string): LeadNote => ({ id, at: "2026-10-22T05:00:00Z", author: { id: "c1", full_name: "Cara Counselor" }, body });
const page = (items: LeadNote[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const URL = "/api/v1/counselor/leads/L1/notes";

let fetchMock: ReturnType<typeof vi.fn>;
let stored: LeadNote[];
let postStatus: number;
beforeEach(() => {
  stored = [note("n1", "First call went well")];
  postStatus = 201;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      if (postStatus !== 201) return Promise.resolve(res({ detail: "Lead not found" }, postStatus));
      const created = note(`n${stored.length + 1}`, JSON.parse(String(init.body)).body);
      stored = [created, ...stored];
      return Promise.resolve(res(created, 201));
    }
    return Promise.resolve(res(page(stored)));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadNotes", () => {
  it("lists the notes with author and full text", async () => {
    render(<LeadNotes url={URL} />);
    const list = await screen.findByRole("list", { name: "Lead notes" });
    expect(within(list).getByText("First call went well")).toBeTruthy();
    expect(within(list).getByText(/Cara Counselor/)).toBeTruthy();
    // QA-01: the list is all notes -- no "Note added" title or "Note" badge on each
    expect(within(list).queryByText("Note added")).toBeNull();
    expect(within(list).queryByText("Note")).toBeNull();
  });

  it("says when there are no notes yet", async () => {
    stored = [];
    render(<LeadNotes url={URL} />);
    expect(await screen.findByText("No notes yet.")).toBeTruthy();
  });

  it("adds a trimmed note, clears the box, re-reads the list and tells the page", async () => {
    const onAdded = vi.fn();
    render(<LeadNotes url={URL} onAdded={onAdded} />);
    await screen.findByText("First call went well");
    const box = screen.getByLabelText("Add a note");
    fireEvent.change(box, { target: { value: "  Father prefers Sunday  " } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("Father prefers Sunday")).toBeTruthy();
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, i]) => i?.method === "POST")?.[1]?.body))).toEqual({ body: "Father prefers Sunday" });
    expect((box as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByRole("status")).toHaveTextContent("Note added.");
    expect(onAdded).toHaveBeenCalledTimes(1);
  });

  it("refuses an empty note without a request", async () => {
    render(<LeadNotes url={URL} />);
    await screen.findByText("First call went well");
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write a note first.");
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);
  });

  it("caps the box at 4000 characters and shows the count", async () => {
    render(<LeadNotes url={URL} />);
    const box = screen.getByLabelText("Add a note") as HTMLTextAreaElement;
    expect(box.maxLength).toBe(4000);
    fireEvent.change(box, { target: { value: "abc" } });
    expect(screen.getByText("3 / 4000")).toBeTruthy();
  });

  it("keeps the text and shows the API's message when the save fails", async () => {
    postStatus = 404;
    const onAdded = vi.fn();
    render(<LeadNotes url={URL} onAdded={onAdded} />);
    await screen.findByText("First call went well");
    const box = screen.getByLabelText("Add a note") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Lead not found"));
    expect(box.value).toBe("Keep me");
    expect(onAdded).not.toHaveBeenCalled();
  });
});
