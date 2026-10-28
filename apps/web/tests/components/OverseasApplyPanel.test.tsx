import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OverseasApplyPanel from "@/components/OverseasApplyPanel";

// nehn-034 (DEC-SCOPE-286 C6): the apply form starts with a country choice that narrows the university list.
const nav = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const COUNTRIES = [
  { id: "uk", slug: "united-kingdom", name: "United Kingdom", university_count: 2 },
  { id: "ca", slug: "canada", name: "Canada", university_count: 1 },
  { id: "jp", slug: "japan", name: "Japan", university_count: 0 },
];
const UNIVERSITIES = [
  { id: "u1", country_id: "uk", slug: "oxford", name: "Oxford", city: "Oxford" },
  { id: "u2", country_id: "uk", slug: "leeds", name: "Leeds", city: "Leeds" },
  { id: "u3", country_id: "ca", slug: "toronto", name: "Toronto", city: "Toronto" },
];

function respond(url: string) {
  const body = url === "/api/v1/public/countries" ? COUNTRIES : url === "/api/v1/public/universities" ? UNIVERSITIES : url.includes("/student/applications") ? { rows: [] } : { courses: [] };
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const universityOptions = () => Array.from((screen.getByLabelText("University") as HTMLSelectElement).options).map((o) => o.textContent);

beforeEach(() => {
  nav.search = "";
  vi.stubGlobal("fetch", vi.fn((url: string) => respond(url)));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OverseasApplyPanel country step", () => {
  it("offers All countries plus only the countries that have universities, before the university", async () => {
    render(<OverseasApplyPanel />);
    const country = (await screen.findByLabelText("Country")) as HTMLSelectElement;
    expect(Array.from(country.options).map((o) => o.textContent)).toEqual(["All countries", "United Kingdom", "Canada"]);
    expect(country.compareDocumentPosition(screen.getByLabelText("University")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(universityOptions()).toEqual(["Select a university…", "Oxford -- Oxford", "Leeds -- Leeds", "Toronto -- Toronto"]);
  });

  it("narrows the universities to the chosen country", async () => {
    render(<OverseasApplyPanel />);
    fireEvent.change(await screen.findByLabelText("Country"), { target: { value: "ca" } });
    expect(universityOptions()).toEqual(["Select a university…", "Toronto -- Toronto"]);
  });

  it("clears a chosen university from another country", async () => {
    render(<OverseasApplyPanel />);
    fireEvent.change(await screen.findByLabelText("University"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "ca" } });
    expect((screen.getByLabelText("University") as HTMLSelectElement).value).toBe("");
    expect((screen.getByRole("button", { name: "Submit interest" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps the university when its own country is chosen", async () => {
    render(<OverseasApplyPanel />);
    fireEvent.change(await screen.findByLabelText("University"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "uk" } });
    expect((screen.getByLabelText("University") as HTMLSelectElement).value).toBe("u1");
  });

  it("preselects the country from ?country=<slug>", async () => {
    nav.search = "country=canada";
    render(<OverseasApplyPanel />);
    await waitFor(() => expect((screen.getByLabelText("Country") as HTMLSelectElement).value).toBe("ca"));
    expect(universityOptions()).toEqual(["Select a university…", "Toronto -- Toronto"]);
  });

  it("ignores an unknown ?country= slug", async () => {
    nav.search = "country=atlantis";
    render(<OverseasApplyPanel />);
    expect(((await screen.findByLabelText("Country")) as HTMLSelectElement).value).toBe("");
    expect(universityOptions()).toHaveLength(4);
  });

  it("still lets the student apply when the country list fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => (url === "/api/v1/public/countries" ? Promise.resolve(new Response("", { status: 500 })) : respond(url))));
    render(<OverseasApplyPanel />);
    expect(Array.from(((await screen.findByLabelText("Country")) as HTMLSelectElement).options).map((o) => o.textContent)).toEqual(["All countries"]);
    expect(universityOptions()).toHaveLength(4);
  });
});

describe("OverseasApplyPanel intake (ccrm-047)", () => {
  it("submits the intake chosen with the month + year picker", async () => {
    const year = String(new Date().getFullYear() + 1);
    render(<OverseasApplyPanel />);
    fireEvent.change(await screen.findByLabelText("University"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Jan" } });
    fireEvent.change(screen.getByLabelText("Intake year"), { target: { value: year } });
    fireEvent.click(screen.getByRole("button", { name: "Submit interest" }));
    const fetchMock = vi.mocked(fetch);
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({ university_id: "u1", intake: `Jan ${year}` });
  });

  it("asks for both parts of the intake before submitting", async () => {
    render(<OverseasApplyPanel />);
    fireEvent.change(await screen.findByLabelText("University"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Jan" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit interest" }));
    expect(await screen.findByText("Choose both the month and the year for the intake.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
