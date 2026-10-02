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
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(ORG));
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
});
