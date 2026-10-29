import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityForm from "@/components/UniversityForm";
import type { University } from "@/lib/universities";

// ccrm-050 (DEC-SCOPE-323): the agent-Master commission fieldset on Add/Edit University, for super_admin / overseas_admin only.
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const countries = { items: [{ id: "gb", label: "United Kingdom", detail: "GB · UK" }], truncated: false };

function route(write: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    String(url).startsWith("/api/v1/lookups/countries") ? Promise.resolve(res(countries))
      : String(url).includes("/universities/duplicates?") ? Promise.resolve(res({ items: [], total: 0 }))
        : Promise.resolve(write));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const writes = (mock: ReturnType<typeof route>) => mock.mock.calls.filter(([, init]) => init?.method !== undefined);
const body = (mock: ReturnType<typeof route>) => JSON.parse(String(writes(mock)[0][1]!.body));

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

const commission = () => screen.getByRole("group", { name: "Agent Master commission" });

const existing = (agent_commission: unknown) => ({
  id: "u7", name: "Old Name", city: "Leeds", country: { id: "gb", name: "United Kingdom", iso2: "GB", region: "UK", catalogue_visible: true },
  institution_type: "university", ownership_type: null, state_region: null, website: null, course_levels: [], popular_programs: [],
  international_office: null, existing_relationship: null, priority: null, partnership_potential: null, overview: "", eligibility: "",
  rankings: [], agent_commission,
}) as unknown as University;

describe("UniversityForm agent commission (ccrm-050)", () => {
  it("is not shown, and not sent, without canEditAgentCommission (partnership roles)", async () => {
    const mock = route(res({ university: { id: "n1" } }, 201));
    render(<UniversityForm />);
    expect(screen.queryByRole("group", { name: "Agent Master commission" })).toBeNull();
    expect(screen.queryByLabelText("Percent")).toBeNull();
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(body(mock)).not.toHaveProperty("agent_commission");
  });

  it("creates with a 10% commission and its note in the same request", async () => {
    const mock = route(res({ university: { id: "n1" } }, 201));
    render(<UniversityForm canEditAgentCommission />);
    expect(within(commission()).getByText(/only an agent Master sees it/)).toBeInTheDocument();
    await fillRequired();
    fireEvent.change(screen.getByLabelText("Percent"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: " Standard rate " } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/n1"));
    expect(writes(mock)).toHaveLength(1);
    expect(body(mock).agent_commission).toEqual({ percent: "10", note: "Standard rate" });
  });

  it("sends null on create when the rate is left blank", async () => {
    const mock = route(res({ university: { id: "n1" } }, 201));
    render(<UniversityForm canEditAgentCommission />);
    await fillRequired();
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(body(mock).agent_commission).toBeNull();
  });

  it("checks a fixed amount needs its currency before sending", async () => {
    const mock = route(res({ university: { id: "n1" } }, 201));
    render(<UniversityForm canEditAgentCommission />);
    await fillRequired();
    fireEvent.click(screen.getByLabelText("Fixed amount"));
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "4000" } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    expect(await screen.findByText("Choose the currency.")).toBeInTheDocument();
    expect(commission()).toHaveAttribute("aria-describedby", "uni-agent_commission-error");
    expect(writes(mock)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "GBP" } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(body(mock).agent_commission).toEqual({ amount: "4000", currency: "GBP" });
  });

  it("shows a 422 on the commission under the fieldset", async () => {
    route(res({ detail: [{ loc: ["body", "agent_commission", "percent"], msg: "Input should be less than or equal to 100" }] }, 422));
    render(<UniversityForm canEditAgentCommission />);
    await fillRequired();
    fireEvent.change(screen.getByLabelText("Percent"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Add university" }));
    expect(await screen.findByText("Input should be less than or equal to 100")).toBeInTheDocument();
    expect(screen.getByLabelText("Percent")).toHaveValue(50);
  });

  it("prefills on edit and a blank rate clears it", async () => {
    const mock = route(res({ university: { id: "u7" } }));
    render(<UniversityForm university={existing({ percent: null, amount: "4000.00", currency: "GBP", note: "Flat" })} canEditAgentCommission />);
    expect(screen.getByLabelText("Fixed amount")).toBeChecked();
    expect(screen.getByLabelText("Amount")).toHaveValue(4000);
    expect(screen.getByLabelText("Currency")).toHaveValue("GBP");
    expect(screen.getByLabelText("Note")).toHaveValue("Flat");
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/partnership/universities/u7"));
    expect(writes(mock)[0][1]!.method).toBe("PATCH");
    expect(body(mock).agent_commission).toBeNull();
  });

  it("re-sends an unchanged percent on edit", async () => {
    const mock = route(res({ university: { id: "u7" } }));
    render(<UniversityForm university={existing({ percent: "16.00", amount: null, currency: null, note: null })} canEditAgentCommission />);
    expect(screen.getByLabelText("Percentage")).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(body(mock).agent_commission).toEqual({ percent: "16.00" });
  });
});
