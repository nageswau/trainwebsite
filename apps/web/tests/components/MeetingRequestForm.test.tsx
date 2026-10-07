import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MeetingRequestForm from "@/components/MeetingRequestForm";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const options = {
  types: [
    { key: "college", label: "College meeting", bdm_type: "college" }, { key: "agent", label: "Agent meeting", bdm_type: "agent" },
    { key: "school", label: "School meeting", bdm_type: "school" }, { key: "corporate", label: "Corporate meeting", bdm_type: "college" },
  ],
  bdms: { college: [{ id: "b-col", full_name: "Anil (college)" }], agent: [{ id: "b-agt", full_name: "Bina (agent)" }], school: [] },
  modes: ["Online", "Phone", "In person"],
};

function route(post: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).endsWith("/options") ? res(options) : post));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockReset();
});

async function fill(type = "corporate") {
  fireEvent.change(await screen.findByLabelText("Meeting type"), { target: { value: type } });
  fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "Infosys Kochi" } });
  fireEvent.change(screen.getByLabelText("Person to meet"), { target: { value: "Ms Menon" } });
  fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "+91 98765 43210" } });
  fireEvent.change(screen.getByLabelText("Proposed date and time (IST)"), { target: { value: "2030-01-02T11:00" } });
  fireEvent.change(screen.getByLabelText("Purpose"), { target: { value: "Campus hiring tie-up" } });
}

describe("MeetingRequestForm (tel-019)", () => {
  it("offers the BDMs of the type's module -- a corporate meeting lists college BDMs (T26)", async () => {
    route(res({}));
    render(<MeetingRequestForm />);
    const bdm = await screen.findByLabelText("BDM");
    expect(bdm.hasAttribute("disabled")).toBe(true); // no type yet
    fireEvent.change(screen.getByLabelText("Meeting type"), { target: { value: "corporate" } });
    const names = Array.from((screen.getByLabelText("BDM") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(names).toEqual(["Any College BDM", "Anil (college)"]);
    fireEvent.change(screen.getByLabelText("BDM"), { target: { value: "b-col" } });
    fireEvent.change(screen.getByLabelText("Meeting type"), { target: { value: "agent" } }); // a type change drops a BDM of another module
    expect((screen.getByLabelText("BDM") as HTMLSelectElement).value).toBe("");
  });

  it("says when a module has no active BDM yet; the request can still go to the pool", async () => {
    route(res({}));
    render(<MeetingRequestForm />);
    fireEvent.change(await screen.findByLabelText("Meeting type"), { target: { value: "school" } });
    expect(screen.getByText(/no active School BDM yet/)).toBeTruthy();
  });

  it("refuses missing fields in place without sending anything", async () => {
    const fetch = route(res({}));
    render(<MeetingRequestForm />);
    fireEvent.click(await screen.findByRole("button", { name: "Send request" }));
    expect(screen.getByText("Choose the meeting type.")).toBeTruthy();
    expect(screen.getByText("Enter the organization.")).toBeTruthy();
    expect(screen.getByText("Enter the purpose.")).toBeTruthy();
    expect(screen.getByLabelText("Meeting type").getAttribute("aria-invalid")).toBe("true");
    expect(fetch).toHaveBeenCalledTimes(1); // the options read only
  });

  it("sends the IST time and the chosen BDM, then returns to the list", async () => {
    const fetch = route(res({ id: "r1", code: "MRQ-000007" }, 201));
    render(<MeetingRequestForm />);
    await fill();
    fireEvent.change(screen.getByLabelText("BDM"), { target: { value: "b-col" } });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/telecaller/meeting-requests?filed=MRQ-000007"));
    const [url, init] = fetch.mock.calls[1];
    expect(url).toBe("/api/v1/telecaller/meeting-requests");
    expect(JSON.parse(String(init?.body))).toEqual({
      request_type: "corporate", bdm_user_id: "b-col", organization_name: "Infosys Kochi", person_name: "Ms Menon", contact_phone: "+91 98765 43210",
      proposed_at: "2030-01-02T11:00:00+05:30", mode: "In person", purpose: "Campus hiring tie-up",
    });
  });

  it("shows the API's field message and keeps the entry", async () => {
    route(res({ detail: [{ type: "value_error", loc: ["body", "proposed_at"], msg: "Choose a time in the future" }] }, 422));
    render(<MeetingRequestForm />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByText("Choose a time in the future")).toBeTruthy();
    expect((screen.getByLabelText("Organization") as HTMLInputElement).value).toBe("Infosys Kochi");
    expect(router.push).not.toHaveBeenCalled();
  });

  it("keeps the entry on a server error", async () => {
    route(res({ detail: "boom" }, 500));
    render(<MeetingRequestForm />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((screen.getByLabelText("Purpose") as HTMLTextAreaElement).value).toBe("Campus hiring tie-up");
  });

  it("offers a retry when the options can't be read", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}, 500))));
    render(<MeetingRequestForm />);
    expect(await screen.findByText(/Unable to load the request form/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
