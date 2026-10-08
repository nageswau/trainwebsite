import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityForm from "@/components/UniversityForm";
import type { University } from "@/lib/universities";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const countries = { items: [{ id: "gb", label: "United Kingdom", detail: "GB · UK" }], truncated: false };
const saved = (id = "u1") => ({ university: { id } });

const NO_MATCHES = { items: [], total: 0 };
const isWrite = ([url, init]: [string, RequestInit?]) => url.startsWith("/api/v1/partnership/universities") && init?.method !== undefined;

// upc-004: the search-before-adding GET answers `matches` (none by default); every other non-country call is the write.
function route(write: Response | (() => Promise<Response>), matches: unknown = NO_MATCHES) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    String(url).startsWith("/api/v1/lookups/countries") ? Promise.resolve(res(countries))
      : String(url).includes("/universities/duplicates?") ? Promise.resolve(res(matches))
        : typeof write === "function" ? write() : Promise.resolve(write));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
});

async function fillRequired() {
  fireEvent.change(screen.getByLabelText("University name (required)"), { target: { value: "ABC University" } });
  const combo = screen.getByRole("combobox", { name: "Country (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "Uni" } });
  fireEvent.click(await screen.findByRole("option", { name: "United Kingdom — GB · UK" }));
  fireEvent.change(screen.getByLabelText("City (required)"), { target: { value: "London" } });
}

const writeBody = (mock: ReturnType<typeof route>, i = 0) => JSON.parse(String(mock.mock.calls.filter(isWrite)[i][1]!.body));

describe("UniversityForm (upc-003 AC1)", () => {
  it("creates with every master field and opens the new university", async () => {
    const mock = route(res(saved("new1"), 201));
    render(<UniversityForm />);
    await fillRequired();
    fireEvent.change(screen.getByLabelText("Institution type"), { target: { value: "college" } });
    fireEvent.change(screen.getByLabelText("Public / private"), { target: { value: "private" } });
    fireEvent.change(screen.getByLabelText("Website"), { target: { value: "abc.ac.uk" } });
    fireEvent.click(screen.getByLabelText("PG"));
    fireEvent.change(screen.getByLabelText("Popular programme areas"), { target: { value: "Business, Engineering , " } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "A" } });
    fireEvent.change(screen.getByLabelText("Partnership potential"), { target: { value: "high" } });
    fireEvent.click(screen.getByRole("button", { name: "Add ranking" }));
    fireEvent.change(screen.getByLabelText("Ranking 1 system"), { target: { value: "QS" } });
    fireEvent.change(screen.getByLabelText("Ranking 1 year"), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText("Ranking 1 rank"), { target: { value: "145" } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/new1"));
    const body = writeBody(mock);
    expect(body).toMatchObject({
      name: "ABC University", country_id: "gb", city: "London", institution_type: "college", ownership_type: "private", website: "abc.ac.uk",
      course_levels: ["PG"], popular_programs: ["Business", "Engineering"], priority: "A", partnership_potential: "high", state_region: null,
      rankings: [{ system: "QS", other_name: null, year: 2026, rank: "145" }],
    });
    expect(mock.mock.calls.find(([url]) => url === "/api/v1/partnership/universities")![1]!.method).toBe("POST");
  });

  it("puts a 422 on its field and keeps the entry", async () => {
    route(res({ detail: [{ loc: ["body", "website"], msg: "Value error, Website must start with http:// or https://" }] }, 422));
    render(<UniversityForm />);
    await fillRequired();
    fireEvent.change(screen.getByLabelText("Website"), { target: { value: "ftp://x" } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    expect(await screen.findByText("Website must start with http:// or https://")).toBeInTheDocument();
    expect(screen.getByLabelText("Website")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("University name (required)")).toHaveValue("ABC University");
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a server message and sends one request on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const mock = route(() => new Promise<Response>((r) => { resolve = r; }));
    render(<UniversityForm />);
    await fillRequired();
    const button = screen.getByRole("button", { name: "Add university" });
    fireEvent.click(button);
    fireEvent.click(button);
    resolve(res({ detail: "Your role cannot add universities" }, 403));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role cannot add universities");
    expect(mock.mock.calls.filter(isWrite)).toHaveLength(1);
  });

  it("edits with PATCH, prefilled, and returns to the detail page", async () => {
    const mock = route(res(saved("u7")));
    const university = {
      id: "u7", name: "Old Name", city: "Leeds", country: { id: "gb", name: "United Kingdom", iso2: "GB", region: "UK", catalogue_visible: true },
      institution_type: "university", ownership_type: null, state_region: null, website: null, course_levels: ["UG"], popular_programs: ["IT"],
      international_office: null, existing_relationship: "existing", priority: null, partnership_potential: null, overview: "", eligibility: "",
      rankings: [{ system: "Other", other_name: "Guardian", year: 2025, rank: "12" }],
    } as unknown as University;
    render(<UniversityForm university={university} />);
    expect(screen.getByLabelText("Ranking 1 name")).toHaveValue("Guardian");
    fireEvent.change(screen.getByLabelText("University name (required)"), { target: { value: "New Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/u7"));
    const call = mock.mock.calls.find(([url]) => url === "/api/v1/partnership/universities/u7")!;
    expect(call[1]!.method).toBe("PATCH");
    expect(JSON.parse(String(call[1]!.body))).toMatchObject({ name: "New Name", country_id: "gb", course_levels: ["UG"], existing_relationship: "existing",
      rankings: [{ system: "Other", other_name: "Guardian", year: 2025, rank: "12" }] });
  });
});

const MATCH = {
  id: "u1", university_code: "UNV-000012", name: "ABC University", country: { id: "gb", name: "United Kingdom" }, city: "London",
  active: true, catalogue_visible: true, existing_relationship: "existing", primary_manager: { id: "m1", full_name: "Rahul Nair", active: true }, backup_manager: null,
};
const duplicate = (can_override: boolean) => ({
  detail: { code: "university_duplicate", message: "This university is already in the University Master", matches: [MATCH], total: 1, can_override },
});

describe("UniversityForm duplicates (upc-004 AC1, UD2, UD6)", () => {
  it("searches before adding and shows the existing university", async () => {
    const mock = route(res(saved(), 201), { items: [MATCH], total: 1 });
    render(<UniversityForm />);
    await fillRequired();
    const panel = await screen.findByRole("status", {}, { timeout: 2000 });
    expect(panel).toHaveTextContent("Already in the University Master");
    expect(panel).toHaveTextContent("Rahul Nair (primary)");
    expect(screen.getByRole("link", { name: "UNV-000012 · ABC University" })).toHaveAttribute("href", "/partnership/universities/u1");
    const searched = mock.mock.calls.map(([url]) => url).find((url) => url.includes("/duplicates?"))!;
    expect(new URL(searched, "http://x").searchParams.get("name")).toBe("ABC University");
    expect(new URL(searched, "http://x").searchParams.get("country_id")).toBe("gb");
  });

  it("blocks a duplicate and lets a head add it anyway with a reason", async () => {
    let calls = 0;
    const mock = route(() => Promise.resolve(++calls === 1 ? res(duplicate(true), 409) : res(saved("dup2"), 201)));
    render(<UniversityForm />);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This university is already in the University Master");
    expect(alert).toHaveTextContent("UNV-000012");
    expect(push).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason for adding it anyway (required)"), { target: { value: "Separate campus with its own office" } });
    fireEvent.click(screen.getByRole("button", { name: "Add anyway" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/dup2"));
    expect(writeBody(mock, 0)).not.toHaveProperty("duplicate_reason");
    expect(writeBody(mock, 1).duplicate_reason).toBe("Separate campus with its own office");
  });

  it("tells a role without the override to ask the head", async () => {
    route(res(duplicate(false), 409));
    render(<UniversityForm />);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ask your partnership head");
    expect(screen.queryByLabelText("Reason for adding it anyway (required)")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add anyway" })).toBeNull();
    expect(screen.getByRole("button", { name: "Add university" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("University name (required)"), { target: { value: "ABC University Dubai" } });
    expect(screen.queryByRole("alert")).toBeNull(); // a corrected name is re-checked on the next save
    expect(screen.getByRole("button", { name: "Add university" })).toBeEnabled();
  });
});
