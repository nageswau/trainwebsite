import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentShortlistForm, { resetCatalogueCache } from "@/components/AgentShortlistForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const catalogue = [{ id: "u1", country_id: "c1", slug: "uni-one", name: "Uni One", city: "Dublin", overview: "", eligibility: "", requirements: ["IELTS 6.5", "Transcript"], deadlines: [], scholarships: [] }];
const countries = [{ id: "c1", slug: "ireland", name: "Ireland" }];
const agency = { items: [{ id: "a1", name: "Agency U", country: "Malta", city: null, entry_requirements: "Interview", created_at: "", updated_at: "" }], total: 1, limit: 100, offset: 0 };
const detail = { university: catalogue[0], courses: [{ id: "k1", title: "MSc Data", level: "PG", tuition_fee: "EUR 20,000", intake: "Sep 2027" }] };
const saved = { id: "e1", university: { source: "catalogue", id: "u1", name: "Uni One", slug: "uni-one", country: "Ireland" }, course: { id: "k1", title: "MSc Data" }, intake: "Sep 2027", tuition_fee: "EUR 20,000", entry_requirements: "IELTS 6.5\nTranscript", created_by: "M", created_at: "", updated_at: "" };

function stubApi(onWrite: (url: string, init: RequestInit) => Response = () => res({ entry: saved }, 201)) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") return Promise.resolve(onWrite(url, init));
    if (url.endsWith("/public/universities")) return Promise.resolve(res(catalogue));
    if (url.endsWith("/public/countries")) return Promise.resolve(res(countries));
    if (url.includes("/public/universities/uni-one")) return Promise.resolve(res(detail));
    if (url.includes("/crm/universities")) return Promise.resolve(res(agency));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => resetCatalogueCache());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const props = { studentId: "s1", mode: "add" as const, onCancel: vi.fn(), onSaved: vi.fn(), onGone: vi.fn(), onConflict: vi.fn() };

describe("AgentShortlistForm (AGN-007)", () => {
  it("offers catalogue and agency universities in two groups", async () => {
    stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(select.querySelector('optgroup[label="Catalogue"] option[value="c:u1"]')).toHaveTextContent("Uni One — Dublin");
    expect(select.querySelector('optgroup[label="Your agency"] option[value="a:a1"]')).toHaveTextContent("Agency U — Malta");
  });

  it("prefills from a catalogue course, never over typed text, and saves the catalogue payload", async () => {
    const fetchMock = stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText("Tuition fee"), { target: { value: "My own fee" } });
    fireEvent.change(select, { target: { value: "c:u1" } });
    expect(await screen.findByText("Ireland")).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("Course"), { target: { value: "k1" } });
    expect(screen.getByLabelText("Intake")).toHaveValue("Sep 2027");
    expect(screen.getByLabelText("Tuition fee")).toHaveValue("My own fee");
    expect(screen.getByLabelText("Entry requirements")).toHaveValue("IELTS 6.5\nTranscript");
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ university_id: "u1", agent_university_id: null, course_id: "k1", course_title: null, intake: "Sep 2027", tuition_fee: "My own fee", entry_requirements: "IELTS 6.5\nTranscript" });
  });

  it("uses a typed course for an agency university and resets the course on change", async () => {
    stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(select, { target: { value: "c:u1" } });
    fireEvent.change(await screen.findByLabelText("Course"), { target: { value: "k1" } });
    fireEvent.change(select, { target: { value: "a:a1" } });
    const course = screen.getByLabelText("Course");
    expect(course.tagName).toBe("INPUT");
    expect(course).toHaveValue("");
    expect(screen.getByText("Malta")).toBeInTheDocument();
  });

  it("shows the server's 422 detail inline", async () => {
    stubApi(() => res({ detail: "Course does not belong to selected university" }, 422));
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(select, { target: { value: "a:a1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Course does not belong to selected university");
  });

  it("requires a university before sending", async () => {
    const fetchMock = stubApi();
    render(<AgentShortlistForm {...props} />);
    await waitFor(() => expect(screen.getByLabelText("University (required)")).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a university.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("closes the form on Escape without closing the detail", async () => {
    stubApi();
    const outer = vi.fn();
    render(<div onKeyDown={outer}><AgentShortlistForm {...props} /></div>);
    fireEvent.keyDown(await screen.findByLabelText("University (required)"), { key: "Escape" });
    expect(props.onCancel).toHaveBeenCalled();
    expect(outer).not.toHaveBeenCalled();
  });

  it("moves focus to the heading on mount and marks the load failure as an alert with Retry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}, 500))));
    render(<AgentShortlistForm {...props} />);
    expect(screen.getByRole("heading", { level: 6 })).toHaveFocus();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load universities.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("drops a stale course list when the university changes again", async () => {
    let release: (r: Response) => void = () => {};
    const slow = new Promise<Response>((resolve) => (release = resolve));
    const fetchMock = stubApi();
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => (url.includes("/public/universities/uni-one") ? slow : base(url, init)));
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(select, { target: { value: "c:u1" } });
    fireEvent.change(select, { target: { value: "a:a1" } });
    release(res(detail));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByLabelText("Course").tagName).toBe("INPUT");
  });
});
