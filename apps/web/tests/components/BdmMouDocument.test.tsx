import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMouDocument from "@/components/BdmMouDocument";
import { mou, res } from "./BdmMouFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const pdf = (name = "signed.pdf", type = "application/pdf", size = 10) => new File([new Uint8Array(size)], name, { type });
const withDocument = mou("signed", { has_document: true, document: { name: "signed.pdf", content_type: "application/pdf", uploaded_at: "2026-10-06T05:00:00Z" } });

describe("BdmMouDocument (bdm-005 M4, AC4)", () => {
  it("downloads through the scoped route, never a file path", () => {
    render(<BdmMouDocument orgId="o1" mou={withDocument} onUploaded={vi.fn()} />);
    const link = screen.getByRole("link", { name: "Download document (PDF)" });
    expect(link).toHaveAttribute("href", "/api/v1/bdm/mous/m1/document");
    expect(link).toHaveAttribute("download");
    expect(screen.getByText(/signed\.pdf/)).toBeInTheDocument();
  });

  it("uploads as multipart PUT and hands back the MoU", async () => {
    const after = { ...withDocument, id: "m1" };
    const fetchMock = vi.fn().mockResolvedValue(res({ mou: after }));
    vi.stubGlobal("fetch", fetchMock);
    const onUploaded = vi.fn();
    render(<BdmMouDocument orgId="o1" mou={mou()} onUploaded={onUploaded} />);
    fireEvent.change(screen.getByLabelText(/Upload document/), { target: { files: [pdf()] } });
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(after));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/mou/document");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(FormData);
  });

  it.each([
    [413, "The file must be at most 20 MB"],
    [415, "Upload a PDF, JPEG or PNG file"],
    [429, "Too many uploads. Try again later."],
  ])("shows the server's %s refusal", async (status, detail) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail }, status)));
    render(<BdmMouDocument orgId="o1" mou={mou()} onUploaded={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Upload document/), { target: { files: [pdf()] } });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(detail));
  });

  it("refuses an obviously wrong file before sending it", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmMouDocument orgId="o1" mou={mou()} onUploaded={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Upload document/), { target: { files: [pdf("notes.txt", "text/plain")] } });
    expect(screen.getByRole("alert")).toHaveTextContent("Upload a PDF, JPEG or PNG file");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("offers no upload without the right, and says when nothing is on file", () => {
    render(<BdmMouDocument orgId="o1" mou={mou("prospect", { permissions: { can_edit: false, can_upload: false, can_renew: false } })} onUploaded={vi.fn()} />);
    expect(screen.queryByLabelText(/Upload document|Replace document/)).toBeNull();
    expect(screen.getByText("No document on file.")).toBeInTheDocument();
  });
});
