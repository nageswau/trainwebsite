import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationReassign from "@/components/BdmOrganizationReassign";
import type { Organization } from "@/lib/bdmOrganizations";

// bdm-002 AC4: the manager picks an active BDM of the organization's type from their team, confirms, and the API decides.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ORG = { id: "o1", code: "ORG-000001", bdm_type: "college", assigned_bdm: { id: "b1", full_name: "Asha", active: true } } as unknown as Organization;
const TEAM = {
  items: [
    { id: "b1", full_name: "Asha", email: "a@x", active: true, employee_id: "E1" },
    { id: "b2", full_name: "Ravi", email: "r@x", active: true, employee_id: "E2" },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};
function serve(assign: () => Response) {
  const mock = vi.fn((url: string) => Promise.resolve(String(url).startsWith("/api/v1/bdm/manager/team") ? res(TEAM) : assign()));
  vi.stubGlobal("fetch", mock);
  return mock;
}
async function pickRavi() {
  const input = screen.getByRole("combobox", { name: "Reassign to" });
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "ra" } });
  fireEvent.click(await screen.findByRole("option", { name: /Ravi/ }));
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationReassign", () => {
  it("searches the team by type, hides the current assignee, confirms and posts", async () => {
    const updated = { ...ORG, assigned_bdm: { id: "b2", full_name: "Ravi", active: true } };
    const mock = serve(() => res({ organization: updated }));
    const onChanged = vi.fn();
    render(<BdmOrganizationReassign organization={ORG} onChanged={onChanged} />);
    await pickRavi();
    expect(String(mock.mock.calls[0][0])).toContain("bdm_type=college");
    expect(screen.queryByRole("option", { name: /Asha/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    expect(screen.getByRole("group", { name: "Confirm reassign" })).toHaveTextContent("Reassign ORG-000001 to Ravi?");
    fireEvent.click(screen.getByRole("button", { name: "Yes, reassign" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated, "Reassigned to Ravi."));
    const [url, init] = mock.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/bdm/organizations/o1/assign");
    expect(JSON.parse(String(init.body))).toEqual({ bdm_user_id: "b2" });
  });

  it("shows the server's refusal", async () => {
    serve(() => res({ detail: "Choose an active BDM of this type from your team" }, 422));
    render(<BdmOrganizationReassign organization={ORG} onChanged={vi.fn()} />);
    await pickRavi();
    fireEvent.click(screen.getByRole("button", { name: "Reassign" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, reassign" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an active BDM of this type from your team");
  });
});
