import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityForm from "@/components/UniversityForm";
import type { University } from "@/lib/universities";

// nehn-035 (DEC-SCOPE-331 L1, L5): an editor uploads the logo from the edit form; the stored URL fills the Logo URL field (so Save keeps it).
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const UPLOADED = "/api/v1/public/university-logos/0123456789abcdef0123456789abcdef.png";
const university = {
  id: "u7", name: "Old Name", city: "Leeds", country: { id: "gb", name: "United Kingdom", iso2: "GB", region: "UK", catalogue_visible: true },
  institution_type: "university", ownership_type: null, state_region: null, website: null, course_levels: [], popular_programs: [],
  international_office: null, existing_relationship: null, priority: null, partnership_potential: null, overview: "", eligibility: "", rankings: [],
  logo_url: null,
} as unknown as University;

function route(upload: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) =>
    url.endsWith("/logo") ? Promise.resolve(upload) : init?.method === "PATCH" ? Promise.resolve(res({ university: { id: "u7" } })) : Promise.resolve(res({ items: [], total: 0 })));
  vi.stubGlobal("fetch", mock);
  return mock;
}

const file = (size = 2048, type = "image/png", name = "logo.png") => new File([new Uint8Array(size)], name, { type });
const choose = (f: File) => fireEvent.change(screen.getByLabelText("Upload a logo"), { target: { files: [f] } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("UniversityForm logo upload (nehn-035)", () => {
  it("uploads the file, previews it, fills the Logo URL field and keeps it on Save", async () => {
    const mock = route(res({ university: { id: "u7", logo_url: UPLOADED } }));
    render(<UniversityForm university={university} />);
    choose(file());
    expect(await screen.findByText("Logo uploaded.")).toBeTruthy();
    const call = mock.mock.calls.find(([url]) => url === "/api/v1/partnership/universities/u7/logo")!;
    expect(call[1]!.method).toBe("PUT");
    expect((call[1]!.body as FormData).get("file")).toBeInstanceOf(File);
    expect(screen.getByLabelText("Logo URL")).toHaveValue(UPLOADED);
    expect(screen.getByRole("img", { name: "Old Name logo" }).getAttribute("src")).toBe(UPLOADED);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/u7"));
    const patch = mock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]!.body)).logo_url).toBe(UPLOADED);
  });

  it("shows the server's refusal and leaves the field alone", async () => {
    route(res({ detail: "This file type is not allowed" }, 415));
    render(<UniversityForm university={university} />);
    choose(file());
    expect(await screen.findByText("This file type is not allowed")).toBeTruthy();
    expect(screen.getByLabelText("Logo URL")).toHaveValue("");
  });

  it("refuses a file over 1 MB or of another type before sending it", () => {
    const mock = route(res({}));
    render(<UniversityForm university={university} />);
    choose(file(1024 * 1024 + 1));
    expect(screen.getByText("Choose a PNG, JPEG or WebP image of at most 1 MB.")).toBeTruthy();
    choose(file(100, "image/svg+xml", "logo.svg"));
    expect(screen.getByText("Choose a PNG, JPEG or WebP image of at most 1 MB.")).toBeTruthy();
    expect(mock.mock.calls.some(([url]) => url.endsWith("/logo"))).toBe(false);
  });

  it("keeps the form usable when the upload cannot reach the server", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    render(<UniversityForm university={university} />);
    choose(file());
    expect(await screen.findByText(/could not be uploaded/i)).toBeTruthy();
    expect(screen.getByLabelText("Upload a logo")).toBeEnabled();
  });

  it("asks to save first when adding a university", () => {
    route(res({}));
    render(<UniversityForm />);
    expect(screen.queryByLabelText("Upload a logo")).toBeNull();
    expect(screen.getByText("Save the university first, then upload its logo here.")).toBeTruthy();
  });
});
