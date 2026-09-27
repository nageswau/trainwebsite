import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import InternshipCertificate from "@/components/InternshipCertificate";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function pick(file: File) {
  fireEvent.change(screen.getByLabelText(/Upload certificate|Replace certificate/), { target: { files: [file] } });
}

describe("InternshipCertificate (ENH-021)", () => {
  it("refuses a wrong type before uploading", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["x"], "a.txt", { type: "text/plain" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Certificate must be a PDF, JPEG or PNG file");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads and announces the result politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ has_certificate: true, content_type: "application/pdf" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Certificate saved.");
    expect(screen.getByRole("link", { name: "Download certificate (PDF)" })).toHaveAttribute("href", "/api/v1/school/students/s/portfolio/entries/e/certificate");
  });

  it("shows the server's message on 413", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 413, json: async () => ({ detail: "certificate must be at most 5 MB" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("certificate must be at most 5 MB");
  });

  it("is download-only for readers and absent when there is nothing to show", () => {
    const { rerender, container } = render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="image/png" canEdit={false} completed />);
    expect(screen.getByRole("link", { name: "Download certificate (image)" })).toBeInTheDocument();
    expect(container.querySelector("input[type=file]")).toBeNull();
    rerender(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed={false} />);
    expect(container.querySelector("input[type=file]")).toBeNull();
  });

  it("requires confirmation to remove", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="application/pdf" canEdit completed />);
    fireEvent.click(screen.getByRole("button", { name: "Remove certificate" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s/portfolio/entries/e/certificate", { method: "DELETE" }));
  });
});
