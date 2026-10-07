import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerManagersCard from "@/components/AdminTelecallerManagersCard";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const meena = { id: "m1", full_name: "Meena", email: "meena@x.local", telecaller_count: 3 };
const kiran = { id: "m2", full_name: "Kiran", email: "kiran@x.local", telecaller_count: 0 };

type Mock = ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
function route(list: Response = res(page([meena, kiran])), post: Response = res({ id: "m1", active: false, moved_telecallers: 3 })): Mock {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((_url, init) =>
    Promise.resolve((init?.method === "POST" ? post : list).clone()));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminTelecallerManagersCard (tel-025 D4)", () => {
  it("lists managers with their telecaller counts; a failed load offers Retry", async () => {
    const mock = route(res({ detail: "boom" }, 500));
    render(<AdminTelecallerManagersCard onChanged={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the telecaller managers list.");
    mock.mockImplementation(() => Promise.resolve(res(page([meena, kiran]))));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("3 telecallers")).toBeInTheDocument();
    expect(screen.getByText("0 telecallers")).toBeInTheDocument();
  });

  it("a manager with telecallers needs a replacement, never themself", async () => {
    const mock = route();
    const onChanged = vi.fn();
    render(<AdminTelecallerManagersCard onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Meena" }));
    const confirm = screen.getByRole("button", { name: "Confirm deactivate" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox", { name: "Replacement manager" }), { target: { value: "k" } });
    expect(await screen.findByRole("option", { name: /Kiran/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Meena/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: /Kiran/ }));
    fireEvent.click(confirm);
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Meena. 3 telecallers now report to Kiran."));
    const [url, init] = mock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(String(url)).toBe("/api/v1/admin/telecaller-managers/m1/deactivate");
    expect(JSON.parse(String(init?.body))).toEqual({ reassign_to: "m2" });
  });

  it("a manager with no telecallers is deactivated directly", async () => {
    const mock = route(res(page([kiran])), res({ id: "m2", active: false, moved_telecallers: 0 }));
    const onChanged = vi.fn();
    render(<AdminTelecallerManagersCard onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Kiran" }));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deactivated Kiran."));
    expect(JSON.parse(String(mock.mock.calls.find(([, i]) => i?.method === "POST")![1]?.body))).toEqual({});
  });

  it("shows the server's sentence on a refusal", async () => {
    route(res(page([meena, kiran])), res({ detail: "Choose another active telecaller manager" }, 422));
    render(<AdminTelecallerManagersCard onChanged={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Meena" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Replacement manager" }), { target: { value: "k" } });
    fireEvent.click(await screen.findByRole("option", { name: /Kiran/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("Choose another active telecaller manager")).toBeInTheDocument();
  });
});
