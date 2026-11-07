import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyVendor from "@/components/RecruiterCompanyVendor";
import { companyBody, type Company, valuesOf } from "@/lib/recruiterCompanies";
import { companyContractsUrl } from "@/lib/recruiterContracts";

const vendor = {
  specialisations: ["Java"], service_categories: [], locations: ["Pune"], onboarding_form_on_file: true, nda_on_file: false, agreement: null,
  next_statuses: [{ status: "registration_submitted", label: "Registration submitted", needs_reason: false }, { status: "suspended", label: "Suspended", needs_reason: true }],
  history: [{ from_status: "prospect", to_status: "prospect", to_label: "Prospect", reason: "Bad form", actor: { id: "u", full_name: "Asha Rao", active: true }, created_at: "2026-11-07T05:00:00Z" }],
};
const company = {
  id: "c1", partner_type: "vendor", vendor_status: "prospect", vendor_status_label: "Prospect", archived: false, vendor,
  permissions: { can_edit: true, can_archive: true, can_restore: false, can_reassign: false },
} as unknown as Company;

function respond(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}
const sent = () => {
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  return { url: String(url), body: JSON.parse(String(init?.body)) };
};

describe("pob-010 vendor card", () => {
  beforeEach(() => respond(200, { company: { ...company, id: "c1" } }));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the status as text, what is on file, and a history", () => {
    render(<RecruiterCompanyVendor company={company} onChanged={() => undefined} />);
    expect(screen.getByText("Not on file")).toBeTruthy();
    expect(screen.getByText("On file")).toBeTruthy();
    expect(screen.getByText("No agreement yet")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Vendor onboarding statuses" }).querySelector("[aria-current=step]")?.textContent).toContain("Prospect");
    expect(screen.getByText(/Bad form/)).toBeTruthy();
  });

  it("moves with the status it was showing and reports the change", async () => {
    const changed = vi.fn();
    render(<RecruiterCompanyVendor company={company} onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Move to Registration submitted" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(sent()).toEqual({ url: "/api/v1/recruiter/companies/c1/vendor-status", body: { status: "registration_submitted", from_status: "prospect" } });
    expect(changed.mock.calls[0][1]).toBe("Vendor moved to Registration submitted.");
  });

  it("asks for the reason a step needs before sending it", async () => {
    render(<RecruiterCompanyVendor company={company} onChanged={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Move to Suspended" }));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Reason for moving to Suspended/), { target: { value: "Late payments" } });
    fireEvent.click(screen.getByRole("button", { name: "Move to Suspended" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(sent().body.reason).toBe("Late payments");
  });

  it("shows the server's refusal and keeps the card", async () => {
    respond(409, { detail: "Upload the vendor onboarding form first" });
    render(<RecruiterCompanyVendor company={company} onChanged={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Move to Registration submitted" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Upload the vendor onboarding form first");
  });

  it("QA-01: a stale move says where the vendor is now and re-reads it", async () => {
    const moved = { ...company, vendor_status: "approved" };
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => init?.method === "POST"
      ? new Response(JSON.stringify({ detail: { message: "This vendor moved to Approved meanwhile", code: "vendor_status_changed", current_status: "approved" } }), { status: 409, headers: { "Content-Type": "application/json" } })
      : new Response(JSON.stringify({ company: moved }), { status: 200, headers: { "Content-Type": "application/json" } })));
    const changed = vi.fn();
    render(<RecruiterCompanyVendor company={company} onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Move to Registration submitted" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(changed.mock.calls[0][0].vendor_status).toBe("approved");
    expect(changed.mock.calls[0][1]).toBe("This vendor moved to Approved meanwhile.");
  });

  it("offers no moves or edit to a reader", () => {
    const reader = { ...company, permissions: { ...company.permissions, can_edit: false }, vendor: { ...vendor, next_statuses: [] } } as Company;
    render(<RecruiterCompanyVendor company={reader} onChanged={() => undefined} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("saves the lists through the company PATCH", async () => {
    const changed = vi.fn();
    render(<RecruiterCompanyVendor company={company} onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit vendor details" }));
    fireEvent.change(screen.getByLabelText("Locations"), { target: { value: "Pune, Goa ," } });
    fireEvent.click(screen.getByRole("button", { name: "Save vendor details" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(sent().body).toEqual({ vendor_specialisations: ["Java"], vendor_service_categories: [], vendor_locations: ["Pune", "Goa"] });
  });
});

describe("pob-010 helpers", () => {
  it("does not send the default relationship on a create, and sends a vendor", () => {
    const values = valuesOf();
    expect(companyBody({ ...values, name: "A" })).toEqual({ name: "A" });
    expect(companyBody({ ...values, name: "A", partner_type: "vendor" })).toEqual({ name: "A", partner_type: "vendor" });
  });

  it("names the vendor side of a contract only", () => {
    expect(companyContractsUrl("c1")).toBe("/api/v1/recruiter/companies/c1/contracts");
    expect(companyContractsUrl("c1", "client")).toBe("/api/v1/recruiter/companies/c1/contracts");
    expect(companyContractsUrl("c1", "vendor")).toBe("/api/v1/recruiter/companies/c1/contracts?party=vendor");
  });
});
