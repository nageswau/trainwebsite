import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationForm from "@/components/BdmOrganizationForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ORG = { id: "o1", code: "ORG-000001", name: "St Mary", city: "Kochi" };
function serve(...responses: Response[]) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(responses.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const body = (mock: ReturnType<typeof serve>, i = 0) => JSON.parse(String((mock.mock.calls[i] as unknown as [string, RequestInit])[1].body));
function fillRequired() {
  fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
  fireEvent.change(screen.getByLabelText("Organization name (required)"), { target: { value: "St Mary" } });
  fireEvent.change(screen.getByLabelText("City (required)"), { target: { value: "Kochi" } });
  fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Dr Rao" } });
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationForm (bdm-002 AC1, AC2, §12.2 F5)", () => {
  it("checks required fields before sending and marks them invalid", async () => {
    const mock = serve();
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Organization name is required")).toBeInTheDocument();
    expect(screen.getByLabelText("Organization name (required)")).toHaveAttribute("aria-invalid", "true");
    expect(mock).not.toHaveBeenCalled();
  });

  it("creates with contacts, the first one primary", async () => {
    const mock = serve(res({ organization: ORG }, 201));
    const onSaved = vi.fn();
    render(<BdmOrganizationForm mode="create" onSaved={onSaved} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    expect(screen.getAllByLabelText("Contact name (required)")[1]).toHaveFocus();
    fireEvent.change(screen.getAllByLabelText("Contact name (required)")[1], { target: { value: "Ms Iyer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(ORG, true));
    const sent = body(mock);
    expect(sent).toMatchObject({ org_type: "college", name: "St Mary", city: "Kochi", existing_partner: false });
    expect(sent.contacts.map((c: { name: string; is_primary: boolean }) => [c.name, c.is_primary])).toEqual([["Dr Rao", true], ["Ms Iyer", false]]);
    expect(sent).not.toHaveProperty("state");
  });

  it("shows the duplicate warning without links, and Save anyway resends with confirm", async () => {
    const dup = { code: "possible_duplicate", message: "A similar organization already exists in your module", total: 1, matches: [{ id: "x", code: "ORG-000009", name: "ST MARY", city: "Kochi", archived: true, assigned_bdm_name: "Asha" }] };
    const mock = serve(res({ detail: dup }, 409), res({ organization: ORG }, 201));
    const onSaved = vi.fn();
    render(<BdmOrganizationForm mode="create" onSaved={onSaved} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ORG-000009");
    expect(alert).toHaveTextContent("Archived");
    expect(alert.querySelector("a")).toBeNull();
    expect(screen.getByRole("button", { name: "Save organization" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(body(mock, 1).confirm_duplicate).toBe(true);
  });

  it("puts a server 422 on its field and keeps the entry on a network drop", async () => {
    serve(res({ detail: [{ loc: ["body", "website"], msg: "Value error, Website must start with http:// or https://" }] }, 422));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Website"), { target: { value: "mary.edu" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Website must start with http:// or https://")).toBeInTheDocument();
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText(/The request did not complete/)).toBeInTheDocument();
    expect(screen.getByLabelText("Organization name (required)")).toHaveValue("St Mary");
  });

  it("edits only the changed fields, without contacts", async () => {
    const organization = { ...ORG, org_type: "college", state: "Kerala", phone: null, email: null, website: null, existing_partner: false, courses_interested: null, student_count: null } as never;
    const mock = serve(res({ organization: ORG }));
    render(<BdmOrganizationForm mode="edit" organization={organization} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Contact name (required)")).toBeNull();
    fireEvent.click(screen.getByLabelText("Existing partner"));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(String(mock.mock.calls[0][0])).toBe("/api/v1/bdm/organizations/o1");
    expect(body(mock)).toEqual({ existing_partner: true });
  });

  it("puts a contact's server error on that contact, not on the organization's field (final review I1)", async () => {
    serve(res({ detail: [{ loc: ["body", "contacts", 0, "email"], msg: "Value error, Enter a valid email address" }] }, 422));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getAllByLabelText("Email")[1], { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    const [orgEmail, contactEmail] = screen.getAllByLabelText("Email");
    expect(contactEmail).toHaveAttribute("aria-invalid", "true");
    expect(orgEmail).not.toHaveAttribute("aria-invalid");
    await waitFor(() => expect(contactEmail).toHaveFocus());
  });

  it("shows an unmappable 422 as one message", async () => {
    serve(res({ detail: [{ loc: ["body", "contacts"], msg: "Value error, Only one contact can be primary" }] }, 422));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only one contact can be primary");
  });

  it("gives contact 1 the same ids on every render, so server and browser agree (browser QA-09)", () => {
    const first = render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    const id = screen.getByLabelText("Contact name (required)").id;
    first.unmount();
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Contact name (required)").id).toBe(id);
  });

  it("keeps contact ids unique after removing and adding contacts (browser QA-09)", () => {
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove contact 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    const ids = screen.getAllByLabelText("Contact name (required)").map((input) => input.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("returns focus to Save after Go back in the duplicate warning (browser QA-10)", async () => {
    const dup = { code: "possible_duplicate", message: "A similar organization already exists in your module", total: 1, matches: [] };
    serve(res({ detail: dup }, 409));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    fireEvent.click(await screen.findByRole("button", { name: "Go back" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save organization" })).toHaveFocus());
  });

  it("asks before Cancel discards unsaved input (browser QA-11)", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.change(screen.getByLabelText("Organization name (required)"), { target: { value: "St Mary" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });

  it("cancels without asking when nothing was entered", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm");
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });

  it("tells people a plain domain is fine for the website (browser QA-05)", () => {
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("For example stjoseph.edu or https://stjoseph.edu")).toBeInTheDocument();
  });

  it("never reuses a removed contact's key, so its old error does not reappear (simplify review A4)", () => {
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Save organization" })); // contact 2 is blank
    expect(screen.getByText("Contact name is required")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove contact 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    expect(screen.queryByText("Contact name is required")).toBeNull();
    expect(screen.getAllByLabelText("Contact name (required)")[1]).not.toHaveAttribute("aria-invalid");
  });

  it("says '1 more similar organization' in the singular", async () => {
    const dup = { code: "possible_duplicate", message: "A similar organization already exists in your module", total: 11, matches: Array.from({ length: 10 }, (_, i) => ({ id: `m${i}`, code: `ORG-00000${i}`, name: "St Mary", city: "Kochi", archived: false, assigned_bdm_name: "Asha" })) };
    serve(res({ detail: dup }, 409));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("1 more similar organization.")).toBeInTheDocument();
  });
});

const SCHOOL = {
  ...ORG, org_type: "school", state: null, phone: null, email: null, website: null, existing_partner: false, courses_interested: null, student_count: null, address: null,
  profile: { kind: "school", board: "CBSE", school_type: null, grade_from: 6, grade_to: 12 },
} as never;

describe("BdmOrganizationForm profile (bdm-003 AC1, AC2, AC5, AC10, §12.2)", () => {
  it("shows the type's section, tells screen readers it follows the type, and sends only that group", async () => {
    const mock = serve(res({ organization: ORG }, 201));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    expect(screen.getByLabelText("Type (required)")).toHaveAccessibleDescription("The details section below changes with the type.");
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "India" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.change(screen.getByLabelText("Address"), { target: { value: "1 Main Rd\nKochi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock).profile).toEqual({ board: "CBSE" }); // the agent's Country typed earlier is not sent
    expect(body(mock).address).toBe("1 Main Rd\nKochi");
  });

  it("checks the grade order before sending", async () => {
    const mock = serve();
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Lowest grade"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Highest grade"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Lowest grade can't be above the highest grade")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Highest grade")).toHaveFocus());
    expect(mock).not.toHaveBeenCalled();
  });

  it("puts a server profile 422 on its field", async () => {
    serve(res({ detail: [{ loc: ["body", "profile", "board"], msg: "Board is not a field for College organizations" }] }, 422));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Board is not a field for College organizations")).toBeInTheDocument();
    expect(screen.getByLabelText("Board")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText("Board")).toHaveFocus());
  });

  it("edits send only changed profile fields", async () => {
    const mock = serve(res({ organization: SCHOOL }));
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Board")).toHaveValue("CBSE");
    fireEvent.change(screen.getByLabelText("Highest grade"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock)).toEqual({ profile: { grade_to: 10 } });
  });

  it("blocks a type change over entered details and names them", async () => {
    const mock = serve();
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Clear the School details before changing the type: Board, Lowest grade, Highest grade.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Type (required)")).toHaveFocus());
    expect(mock).not.toHaveBeenCalled();
  });

  it("type changed and changed back is not blocked (Review Focus 4)", async () => {
    const mock = serve(res({ organization: SCHOOL }));
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "ICSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock)).toEqual({ profile: { board: "ICSE" } });
  });

  it("shows the server's profile_not_empty 409 under Type", async () => {
    const corporate = { ...(SCHOOL as object), org_type: "corporate", profile: null } as never;
    serve(res({ detail: { code: "profile_not_empty", message: "Clear the School details before changing the type", fields: ["board"] } }, 409));
    render(<BdmOrganizationForm mode="edit" organization={corporate} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Clear the School details before changing the type.")).toBeInTheDocument();
    expect(screen.getByLabelText("Type (required)")).toHaveAttribute("aria-invalid", "true");
  });

  it("never wipes Number of staff when the typed value is not a number (final review I1)", async () => {
    const agent = { ...(SCHOOL as object), org_type: "agent", profile: { kind: "agent", country: null, territory: null, source: null, staff_count: 25 } } as never;
    const mock = serve(res({ detail: [{ loc: ["body", "profile", "staff_count"], msg: "Value error, Number of staff must be a whole number from 0 to 100,000" }] }, 422));
    render(<BdmOrganizationForm mode="edit" organization={agent} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Number of staff"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock)).toEqual({ profile: { staff_count: "abc" } }); // sent as typed: the server names the field, nothing is cleared
    expect(await screen.findByText("Number of staff must be a whole number from 0 to 100,000")).toBeInTheDocument();
  });

  it("explains the two saves when the old details were cleared in this form (final review I2)", async () => {
    const mock = serve();
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    for (const label of ["Board", "Lowest grade", "Highest grade"]) fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Save the cleared School details first: change the type back to School and save, then change the type.")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });

  it("counts profile and address edits as unsaved changes", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onCancel = vi.fn();
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.change(screen.getByLabelText("School type"), { target: { value: "private" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});
