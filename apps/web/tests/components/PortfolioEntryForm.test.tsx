import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PortfolioEntryForm", () => {
  it("requires a title before submitting", async () => {
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/enter a title/i)).toBeInTheDocument();
  });

  it("shows a server error on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "date_to must not be before date_from" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("date_to must not be before date_from");
  });

  it("calls onDone after a successful save", async () => {
    const onDone = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1", section: "project", title: "A project" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={onDone} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("PATCHes to the entry URL and omits section when editing an existing entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1", section: "project", title: "Updated" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" entryId="e1" initial={{ title: "Old", description: null, organization: null, date_from: null, date_to: null }} onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/portfolio/entries/e1", expect.objectContaining({ method: "PATCH" })));
  });
});
