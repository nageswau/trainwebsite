import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityContacts from "@/components/UniversityContacts";
import { RELATIONSHIP_STRENGTHS, type UniversityContact } from "@/lib/universities";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const roles = [{ code: "regional_manager", label: "Regional Manager" }, { code: "finance_contact", label: "Finance Contact" }];
const contact = (over: Partial<UniversityContact> = {}): UniversityContact => ({
  id: "c1", university_id: "u1", name: "Priya Raman", designation: "Regional Manager – India", department: "International Office",
  role: roles[0], email: "priya@abc.ac.uk", phone: "+44 20 7000 0000", whatsapp: "+91 98450 00000", linkedin: "https://linkedin.com/in/priya",
  preferred_channel: "whatsapp", relationship_strength: "strategic", notes: "Prefers mornings", is_primary: true, shareable: true,
  created_at: "", updated_at: "", ...over,
});
const bodyOf = (mock: ReturnType<typeof vi.fn>, i = 0) => JSON.parse(String((mock.mock.calls[i] as [string, RequestInit])[1].body));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityContacts (upc-006)", () => {
  it("shows each contact's §10 fields, the primary badge and the relationship label", () => {
    render(<UniversityContacts universityId="u1" contacts={[contact(), contact({ id: "c2", name: "Ben", is_primary: false, shareable: false, relationship_strength: "at_risk" })]} roles={roles} canEdit={false} />);
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText("Primary")).toBeInTheDocument();
    expect(within(items[0]).getByText("Strategic")).toBeInTheDocument();
    expect(within(items[0]).getByText(/Regional Manager – India/)).toBeInTheDocument();
    expect(within(items[0]).getByRole("link", { name: "https://linkedin.com/in/priya" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(items[0]).getByText(/Prefers: WhatsApp/)).toBeInTheDocument();
    expect(within(items[1]).getByText("At Risk")).toBeInTheDocument();
    expect(within(items[1]).getByText("Internal")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add contact/ })).not.toBeInTheDocument();
  });

  it("uses the seven §11 values exactly", () => {
    expect(Object.values(RELATIONSHIP_STRENGTHS)).toEqual(["New", "Developing", "Good", "Strong", "Strategic", "At Risk", "Dormant"]);
  });

  it("shows an empty state", () => {
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    expect(screen.getByText("No contacts recorded yet.")).toBeInTheDocument();
  });

  it("adds a contact with blanks left out, then refreshes", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ contact: contact() }, 201)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Priya Raman" } });
    fireEvent.change(screen.getByLabelText("Designation"), { target: { value: "Regional Manager – India" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "regional_manager" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "priya@abc.ac.uk" } });
    fireEvent.change(screen.getByLabelText("Relationship strength"), { target: { value: "good" } });
    fireEvent.click(screen.getByLabelText("Visible to counsellors (shareable)"));
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/universities/u1/contacts", expect.objectContaining({ method: "POST" }));
    expect(bodyOf(mock)).toEqual({
      name: "Priya Raman", designation: "Regional Manager – India", role_code: "regional_manager", email: "priya@abc.ac.uk",
      relationship_strength: "good", shareable: true,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Contact added.");
  });

  it("requires a name before sending", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(screen.getByText("Contact name is required")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });

  it("puts a 422 on its field and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "email"], msg: "Value error, Enter a valid email address" }] }, 422))));
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Priya" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "bad@" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Name (required)")).toHaveValue("Priya");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("words a server error plainly and keeps the entry (QA-I1)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("Internal Server Error", { status: 500 }))));
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Priya" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The change could not be saved. Try again.");
    expect(screen.getByLabelText("Name (required)")).toHaveValue("Priya");
  });

  it("keeps the connection message when the request never completes", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Priya" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The request did not complete");
  });

  it("sends one request on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const mock = vi.fn(() => new Promise<Response>((r) => { resolve = r; }));
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Priya" } });
    const save = screen.getByRole("button", { name: "Save contact" });
    fireEvent.click(save);
    fireEvent.click(save);
    resolve(res({ detail: "Another contact at this university already has this email" }, 409));
    expect(await screen.findByRole("alert")).toHaveTextContent("already has this email");
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("edits only the changed fields with PATCH; a cleared field is sent as null", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ contact: contact() })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[contact()]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Priya Raman" }));
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Relationship strength"), { target: { value: "dormant" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/contacts/c1", expect.objectContaining({ method: "PATCH" }));
    expect(bodyOf(mock)).toEqual({ phone: null, relationship_strength: "dormant" });
  });

  it("makes another contact primary", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ contact: contact({ id: "c2" }) })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[contact(), contact({ id: "c2", name: "Ben", is_primary: false })]} roles={roles} canEdit />);
    expect(screen.queryByRole("button", { name: "Make Priya Raman primary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Make Ben primary" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(bodyOf(mock)).toEqual({ is_primary: true });
  });

  it("confirms before deleting and shows a refusal", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ detail: "Make another contact primary before deleting this one" }, 409)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityContacts universityId="u1" contacts={[contact(), contact({ id: "c2", name: "Ben", is_primary: false })]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Delete Priya Raman" }));
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Make another contact primary");
    expect(mock).toHaveBeenCalledWith("/api/v1/partnership/contacts/c1", expect.objectContaining({ method: "DELETE" }));
  });

  it("deletes after confirming", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(null, 204))));
    render(<UniversityContacts universityId="u1" contacts={[contact({ id: "c2", name: "Ben", is_primary: false })]} roles={roles} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Delete Ben" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(await screen.findByRole("status")).toHaveTextContent("Contact deleted.");
  });
});
