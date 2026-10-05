import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import SchoolStudentPhoto from "@/components/SchoolStudentPhoto";

// ENH-025 -- student photo: authorized image, initials fallback, coordinator-only controls (spec §4.3).
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const file = (type: string, size: number) => new File([new Uint8Array(size)], "p", { type });

describe("SchoolStudentPhoto", () => {
  it("shows the initials placeholder when there is no photo", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit={false} />);
    expect(screen.getByRole("img", { name: "No photo for Asha Rao" }).textContent).toBe("AR");
  });

  // QA2-01: an <img> in the server HTML can fail before React hydrates, and then onError never runs (the user saw a
  // broken-image icon). The server HTML carries the placeholder; the image is only created once the component is live.
  it("server-renders the initials placeholder, never an <img>, even when a photo exists", () => {
    const html = renderToString(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit={false} />);
    expect(html).not.toContain("<img");
    expect(html).toContain("No photo for Asha Rao");
  });

  it("renders the image and falls back to the placeholder if it fails to load", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit={false} />);
    const img = screen.getByRole("img", { name: "Photo of Asha Rao" });
    expect(img.getAttribute("src")).toContain("/api/v1/school/students/s1/photo");
    fireEvent.error(img);
    expect(screen.getByRole("img", { name: "No photo for Asha Rao" })).toBeTruthy();
  });

  it("read-only mode shows no controls", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit={false} />);
    expect(screen.queryByLabelText(/upload a photo|replace photo/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove photo" })).toBeNull();
  });

  it("rejects a wrong type or oversize file before uploading", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    const input = screen.getByLabelText(/upload a photo/i);
    fireEvent.change(input, { target: { files: [file("image/gif", 10)] } });
    // QA2-05: same wording as the server's own check for the same problem.
    expect((await screen.findByRole("alert")).textContent).toBe("Photo must be a JPEG or PNG image");
    fireEvent.change(input, { target: { files: [file("image/png", 2 * 1024 * 1024 + 1)] } });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Photo must be at most 2 MB"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads, shows busy state, then the new photo", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    fireEvent.change(screen.getByLabelText(/upload a photo/i), { target: { files: [file("image/png", 10)] } });
    expect(await screen.findByText("Uploading…")).toBeTruthy();
    resolve(new Response(JSON.stringify({ has_photo: true })));
    expect(await screen.findByRole("img", { name: "Photo of Asha Rao" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Photo saved");
  });

  it("remove needs confirmation and can be cancelled", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Remove photo" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove photo" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/photo", { method: "DELETE" }));
    expect(await screen.findByRole("img", { name: "No photo for Asha Rao" })).toBeTruthy();
  });

  it("shows the server's message when upload fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "photo must be a JPEG or PNG image" }), { status: 415 })));
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    fireEvent.change(screen.getByLabelText(/upload a photo/i), { target: { files: [file("image/png", 10)] } });
    // QA2-05: the server's wording, in the user's words.
    expect((await screen.findByRole("alert")).textContent).toBe("Photo must be a JPEG or PNG image");
  });
});
