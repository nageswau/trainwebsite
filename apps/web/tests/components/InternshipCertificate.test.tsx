import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import InternshipCertificate from "@/components/InternshipCertificate";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockClear();
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

  // QA-01 (browser QA 2026-09-28): without a refresh the page's portfolio data still says "no certificate", so the card showed
  // "Upload certificate" again after Edit -> Cancel remounted it.
  it("refreshes the page data after a successful upload and after a removal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ has_certificate: true, content_type: "application/pdf" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    await screen.findByRole("status");
    expect(refresh).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove certificate" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
  });

  // QA-06 (browser QA 2026-09-28): the Confirm button disappears on success, which dropped keyboard focus to <body>.
  it("moves focus to the upload field after a removal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="application/pdf" canEdit completed />);
    fireEvent.click(screen.getByRole("button", { name: "Remove certificate" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await screen.findByRole("status");
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(/Upload certificate/)));
  });

  // QA-07 (browser QA 2026-09-28): as direct children of the .field grid both controls stretched to the card's full width, so the
  // destructive Remove looked exactly like Download. The shared .actions row keeps them at their natural width.
  it("keeps Download and Remove in an actions row, not stretched by the field grid", () => {
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="application/pdf" canEdit completed />);
    expect(screen.getByRole("link", { name: "Download certificate (PDF)" }).parentElement).toHaveClass("actions");
    expect(screen.getByRole("button", { name: "Remove certificate" }).parentElement).toHaveClass("actions");
  });

  it("does not refresh when the upload fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 415, json: async () => ({ detail: "nope" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    await screen.findByRole("alert");
    expect(refresh).not.toHaveBeenCalled();
  });

  // QA-11 (browser QA 2026-09-28): a 5xx showed the bare "Internal Server Error".
  it("words a server failure for people", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({ detail: "Internal Server Error" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
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
