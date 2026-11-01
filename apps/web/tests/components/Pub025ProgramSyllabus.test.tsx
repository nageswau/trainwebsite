import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminProgramManagementPanel from "@/components/AdminProgramManagementPanel";
import CourseShowcase, { pickShowcase } from "@/components/CourseShowcase";
import ProgramMediaEditor from "@/components/ProgramMediaEditor";
import ProgramSyllabus from "@/components/ProgramSyllabus";
import type { Program } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

// PUB-025 (DEC-SCOPE-334): one syllabus source per course (S1), open with no enquiry gate (S2), optional card image (S3).
const base: Program = {
  id: "P1", slug: "python-full-stack", category: "Software Development", title: "Python Full Stack", summary: "Build web apps.", duration: "16 weeks",
  eligibility: "", fees: 1000, certification: "", curriculum: ["Python", "Django"], placement_assistance: "", trainer_name: "",
};
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProgramSyllabus (public course page)", () => {
  it("falls back to the curriculum list when no syllabus is set", () => {
    render(<ProgramSyllabus program={base} />);
    expect(screen.getByRole("heading", { name: "Curriculum" })).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Python", "Django"]);
  });

  it("shows typed modules as expandable sections, the first open", () => {
    const { container } = render(<ProgramSyllabus program={{ ...base, syllabus: { source: "manual", modules: [{ title: "Basics", topics: ["Variables", "Loops"] }, { title: "Django", topics: [] }] } }} />);
    expect(screen.getByRole("heading", { name: "Syllabus" })).toBeTruthy();
    const sections = container.querySelectorAll("details");
    expect(sections).toHaveLength(2);
    expect(sections[0].open).toBe(true);
    expect(sections[1].open).toBe(false);
    expect(within(sections[0] as HTMLElement).getByText("2 topics")).toBeTruthy();
    expect(within(sections[0] as HTMLElement).getByText("Loops")).toBeTruthy();
  });

  it("links a PDF and a Drive link in a new tab with no form in the way", () => {
    render(<ProgramSyllabus program={{ ...base, syllabus: { source: "pdf", url: "/api/v1/public/program-files/abc.pdf" } }} />);
    const pdf = screen.getByRole("link", { name: /Download syllabus \(PDF\)/ });
    expect(pdf.getAttribute("href")).toBe("/api/v1/public/program-files/abc.pdf");
    expect(pdf.getAttribute("target")).toBe("_blank");
    expect(pdf.getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.queryByRole("textbox")).toBeNull();
    cleanup();
    render(<ProgramSyllabus program={{ ...base, syllabus: { source: "link", url: "https://drive.google.com/file/d/1/view" } }} />);
    expect(screen.getByRole("link", { name: /Open syllabus/ }).getAttribute("href")).toBe("https://drive.google.com/file/d/1/view");
  });
});

describe("CourseShowcase (/it home)", () => {
  it("shows at most six cards with image or generated tile and a View Details link", () => {
    const programs = Array.from({ length: 8 }, (_, i) => ({ ...base, id: `P${i}`, slug: `c${i}`, title: `Course ${i}`, image_url: i === 0 ? "/api/v1/public/program-files/x.png" : null }));
    const { container } = render(<CourseShowcase programs={programs} />);
    expect(screen.getByRole("heading", { name: "Explore Our Courses" })).toBeTruthy();
    expect(container.querySelector("#courses-section")).toBeTruthy();
    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(6);
    expect(cards[0].querySelector("img")?.getAttribute("src")).toBe("/api/v1/public/program-files/x.png");
    expect(cards[1].querySelector("img")).toBeNull();
    expect(within(cards[1]).getByText("</>")).toBeTruthy();
    expect(within(cards[2]).getByRole("link", { name: /View Details/ }).getAttribute("href")).toBe("/it/programs/c2");
  });

  it("picks courses with an image first, then one per category in turn", () => {
    const mk = (slug: string, category: string, image = false): Program => ({ ...base, id: slug, slug, category, image_url: image ? `/x/${slug}.png` : null });
    const programs = [mk("ai1", "AI"), mk("ai2", "AI"), mk("ai3", "AI"), mk("c1", "Cloud"), mk("c2", "Cloud"), mk("d1", "Data"), mk("py", "Software", true), mk("sap", "SAP")];
    expect(pickShowcase(programs).map((p) => p.slug)).toEqual(["py", "ai1", "c1", "d1", "sap", "ai2"]);
    expect(pickShowcase(programs, 3).map((p) => p.slug)).toEqual(["py", "ai1", "c1"]);
    expect(pickShowcase([mk("a", "AI")]).map((p) => p.slug)).toEqual(["a"]);
  });

  it("renders nothing without courses", () => {
    const { container } = render(<CourseShowcase programs={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("ProgramMediaEditor (admin)", () => {
  const media = (extra = {}) => ({ id: "P1", slug: "python-full-stack", title: "Python Full Stack", image_url: null, syllabus: null, ...extra });

  it("saves typed modules with topics split by line", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      void url;
      if (init?.method === "PUT") return Promise.resolve(ok(media({ syllabus: { source: "manual", modules: [{ title: "Basics", topics: ["A", "B"] }] } })));
      return Promise.resolve(ok(media()));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProgramMediaEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("radio", { name: "Type modules and topics" }));
    fireEvent.change(screen.getByLabelText("Module 1 title"), { target: { value: "Basics" } });
    fireEvent.change(screen.getByLabelText("Module 1 topics (one per line)"), { target: { value: "A\nB" } });
    fireEvent.click(screen.getByRole("button", { name: "Save syllabus" }));
    expect(await screen.findByText("Syllabus saved.")).toBeTruthy();
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(url).toBe("/api/v1/admin/programs/P1/syllabus");
    expect(JSON.parse(String(init!.body))).toEqual({ source: "manual", modules: [{ title: "Basics", topics: ["A", "B"] }] });
  });

  it("saves a link and shows the server's refusal", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PUT" ? new Response(JSON.stringify({ detail: "The syllabus link must be a full https:// address" }), { status: 422 }) : ok(media())));
    vi.stubGlobal("fetch", fetchMock);
    render(<ProgramMediaEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("radio", { name: "Google Drive or web link" }));
    fireEvent.change(screen.getByLabelText(/Syllabus link/), { target: { value: "http://x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save syllabus" }));
    expect((await screen.findByRole("alert")).textContent).toContain("https://");
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")![1]!.body))).toEqual({ source: "link", url: "http://x" });
  });

  it("uploads a PDF and an image as multipart files", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PUT" && url.endsWith("/syllabus/pdf")) return Promise.resolve(ok(media({ syllabus: { source: "pdf", url: "/api/v1/public/program-files/a.pdf" } })));
      if (init?.method === "PUT" && url.endsWith("/image")) return Promise.resolve(ok(media({ image_url: "/api/v1/public/program-files/b.png" })));
      return Promise.resolve(ok(media()));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProgramMediaEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("radio", { name: "Upload a PDF" }));
    expect((screen.getByRole("button", { name: "Upload PDF" }) as HTMLButtonElement).disabled).toBe(true);
    const pdf = new File(["%PDF-1.4"], "s.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/PDF file, up to 10 MB/), { target: { files: [pdf] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    expect(await screen.findByText("Syllabus PDF uploaded.")).toBeTruthy();
    const pdfCall = fetchMock.mock.calls.find(([u]) => u.endsWith("/syllabus/pdf"))!;
    expect((pdfCall[1]!.body as FormData).get("file")).toBe(pdf);
    expect(screen.getByRole("link", { name: /View the current PDF/ }).getAttribute("href")).toBe("/api/v1/public/program-files/a.pdf");

    const image = new File(["png"], "c.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(/PNG, JPEG or WebP/), { target: { files: [image] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload image" }));
    expect(await screen.findByText("Card image uploaded.")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Current card image for Python Full Stack" }).getAttribute("src")).toBe("/api/v1/public/program-files/b.png");
    expect(screen.getByRole("button", { name: "Remove image" })).toBeTruthy();
  });

  it("loads an existing manual syllabus into the form", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(ok(media({ syllabus: { source: "manual", modules: [{ title: "Intro", topics: ["X", "Y"] }] } })))));
    render(<ProgramMediaEditor programId="P1" programTitle="Python Full Stack" onClose={() => {}} />);
    expect(((await screen.findByLabelText("Module 1 title")) as HTMLInputElement).value).toBe("Intro");
    expect((screen.getByLabelText("Module 1 topics (one per line)") as HTMLTextAreaElement).value).toBe("X\nY");
    expect((screen.getByRole("radio", { name: "Type modules and topics" }) as HTMLInputElement).checked).toBe(true);
  });
});

describe("AdminProgramManagementPanel image & syllabus", () => {
  it("opens one editor at a time under the row and returns focus on Close", async () => {
    const rows = [{ id: "P1", slug: "dotnet", category: "Software", title: ".NET", duration: "8w", fees: 0, active: true }];
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(ok(
      url === "/api/v1/admin/programs" ? rows : url.endsWith("/media") ? { id: "P1", slug: "dotnet", title: ".NET", image_url: null, syllabus: null } : { items: [] },
    ))));
    render(<AdminProgramManagementPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Skills for .NET" }));
    await screen.findByRole("region", { name: "Skills taught in .NET" });
    const media = screen.getByRole("button", { name: "Image and syllabus for .NET" });
    fireEvent.click(media);
    expect(screen.queryByRole("region", { name: "Skills taught in .NET" })).toBeNull();
    expect(await screen.findByRole("region", { name: "Image and syllabus for .NET" })).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Close" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Image and syllabus for .NET" })));
  });
});
