import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmHandover from "@/components/AdminBdmHandover";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, bdm_type: "college" as const, employee_id: "E-1", designation: null,
  department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true }, manager_active: true,
};
const OPEN = { organizations: 3, appointments: 1, tasks: 2, trips: 0 };
const NONE = { organizations: 0, appointments: 0, tasks: 0, trips: 0 };
const bdms = { items: [row, { ...row, id: "b2", full_name: "Ravi", employee_id: "E-2", email: "ravi@x.local" }], total: 2, limit: 20, offset: 0 };

type Mock = ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
/** GET portfolio -> `counts`; BDM search -> Asha + Ravi; POST -> `post`. */
function route(counts: unknown = OPEN, post: Response = res({ id: "b1" })): Mock {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) => {
    const u = String(url);
    if (init?.method === "POST") return Promise.resolve(post.clone());
    if (u.endsWith("/portfolio")) return Promise.resolve(counts instanceof Response ? counts.clone() : res(counts));
    return Promise.resolve(res(bdms));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
const posts = (mock: Mock) => mock.mock.calls.filter(([, init]) => init?.method === "POST");
const postBody = (mock: Mock) => JSON.parse(String(posts(mock)[0][1]?.body));

function mount(mode: "deactivate" | "handover" = "deactivate", overrides: Partial<typeof row> = {}) {
  const onDone = vi.fn();
  const onCancel = vi.fn();
  render(<AdminBdmHandover row={{ ...row, ...overrides }} mode={mode} onDone={onDone} onCancel={onCancel} />);
  return { onDone, onCancel };
}

async function pickRavi() {
  fireEvent.change(screen.getByRole("combobox", { name: "Hand over to" }), { target: { value: "rav" } });
  fireEvent.click(await screen.findByRole("option", { name: /Ravi/ }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminBdmHandover (bdm-025)", () => {
  it("shows a loading state, then the open work to hand over", async () => {
    route();
    mount();
    expect(screen.getByRole("status")).toHaveTextContent("Loading open work…");
    expect(await screen.findByText("Open work: 3 organizations, 1 appointment and 2 follow-ups/tasks.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Deactivate Asha" })).toBeInTheDocument();
  });

  it("a failed count load offers Retry", async () => {
    const mock = route(res({ detail: "boom" }, 500));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load Asha's open work.");
    mock.mockImplementation(() => Promise.resolve(res(OPEN)));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Open work: 3 organizations/)).toBeInTheDocument();
  });

  it("needs a choice before it can confirm (AC1)", async () => {
    route();
    mount();
    const confirm = await screen.findByRole("button", { name: "Confirm deactivate" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Hand over to another BDM" }));
    expect(confirm).toBeDisabled(); // a BDM must be picked too
    await pickRavi();
    expect(confirm).toBeEnabled();
  });

  it("hands over to the picked BDM, excluding the BDM themself from the list", async () => {
    const mock = route(OPEN, res({ id: "b1", active: false, mode: "reassign", moved: { organizations: 3, appointments: 1, tasks: 2 }, trips_cancelled: 0 }));
    const { onDone } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "Hand over to another BDM" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Hand over to" }), { target: { value: "a" } });
    await screen.findByRole("option", { name: /Ravi/ });
    expect(screen.queryByRole("option", { name: /Asha/ })).toBeNull();
    expect(mock.mock.calls.some(([u]) => String(u).includes("bdm_type=college") && String(u).includes("active=true"))).toBe(true);
    fireEvent.click(screen.getByRole("option", { name: /Ravi/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Asha. 3 organizations, 1 appointment and 2 follow-ups/tasks handed over to Ravi."));
    expect(postBody(mock)).toEqual({ mode: "reassign", reassign_to: "b2" });
    expect(posts(mock)[0][0]).toBe("/api/v1/admin/bdms/b1/deactivate");
  });

  it("keeps the work with the BDM when asked", async () => {
    const mock = route(OPEN, res({ id: "b1", active: false, mode: "leave", moved: { organizations: 0, appointments: 0, tasks: 0 }, trips_cancelled: 0 }));
    const { onDone } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "Keep with Asha for now (hand over later)" }));
    expect(screen.queryByRole("combobox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Asha. Their open work stays with them until you hand it over."));
    expect(postBody(mock)).toEqual({ mode: "leave" });
  });

  it("with nothing open, confirms straight away", async () => {
    const mock = route({ ...NONE, trips: 2 }, res({ id: "b1", active: false, mode: "leave", moved: NONE, trips_cancelled: 2 }));
    const { onDone } = mount();
    expect(await screen.findByText("Asha has no open work to hand over.")).toBeInTheDocument();
    expect(screen.getByText("2 trips not yet started will be cancelled.")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Deactivated Asha. 2 not-started trips were cancelled."));
    expect(postBody(mock)).toEqual({ mode: "leave" });
  });

  it("shows a server refusal in an alert and focuses it", async () => {
    route(OPEN, res({ detail: "Choose an active BDM of the same module" }, 422));
    const { onDone } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: "Hand over to another BDM" }));
    await pickRavi();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    const alert = await screen.findByText("Choose an active BDM of the same module");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(onDone).not.toHaveBeenCalled();
  });

  it("disables the buttons while saving, so a double click sends once", async () => {
    let release: (r: Response) => void = () => {};
    const mock = route();
    mock.mockImplementation((url, init) =>
      init?.method === "POST" ? new Promise<Response>((r) => { release = r; }) : Promise.resolve(String(url).endsWith("/portfolio") ? res(OPEN) : res(bdms)));
    mount();
    fireEvent.click(await screen.findByRole("radio", { name: "Keep with Asha for now (hand over later)" }));
    const confirm = screen.getByRole("button", { name: "Confirm deactivate" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByRole("button", { name: "Deactivating…" })).toBeDisabled();
    expect(posts(mock)).toHaveLength(1);
    release(res({ id: "b1", active: false, mode: "leave", moved: NONE, trips_cancelled: 0 }));
  });

  it("Keep active and Escape cancel", async () => {
    route();
    const { onCancel } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Keep active" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole("group", { name: "Deactivate Asha" }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  // QA25-01: the trigger unmounts when the group opens, so the group itself takes focus; Escape works without tabbing in first.
  it("takes focus when it opens, so Escape works straight away", async () => {
    route();
    const { onCancel } = mount();
    const group = screen.getByRole("group", { name: "Deactivate Asha" });
    await waitFor(() => expect(group).toHaveFocus());
    fireEvent.keyDown(document.activeElement as Element, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  // QA25-03: a 5xx is worded for people (bdm-006 QA6-04); a 4xx keeps the server's sentence.
  it.each([
    ["deactivate", "We couldn't deactivate Asha. Please try again."],
    ["handover", "We couldn't hand over Asha's work. Please try again."],
  ] as const)("words a server error in %s mode", async (mode, message) => {
    route(OPEN, res({ detail: "Internal Server Error" }, 500));
    mount(mode, { active: mode === "deactivate" });
    if (mode === "deactivate") fireEvent.click(await screen.findByRole("radio", { name: "Hand over to another BDM" }));
    else await screen.findByText(/Open work/);
    await pickRavi();
    fireEvent.click(screen.getByRole("button", { name: mode === "deactivate" ? "Confirm deactivate" : "Hand over" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("handover mode: picker only, then hands over", async () => {
    const mock = route(OPEN, res({ id: "b1", moved: { organizations: 3, appointments: 1, tasks: 2 } }));
    const { onDone } = mount("handover", { active: false });
    expect(await screen.findByRole("group", { name: "Hand over Asha's open work" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    const button = screen.getByRole("button", { name: "Hand over" });
    expect(button).toBeDisabled();
    await pickRavi();
    fireEvent.click(button);
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Handed over 3 organizations, 1 appointment and 2 follow-ups/tasks from Asha to Ravi."));
    expect(posts(mock)[0][0]).toBe("/api/v1/admin/bdms/b1/handover");
    expect(postBody(mock)).toEqual({ reassign_to: "b2" });
  });

  it("handover mode with nothing open says so and only offers Close", async () => {
    route(NONE);
    const { onCancel } = mount("handover", { active: false });
    expect(await screen.findByText("Asha has no open work to hand over.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hand over" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
