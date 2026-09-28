import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentTeamPanel from "@/components/AgentTeamPanel";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const me = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active", invite_pending: false, is_you: true };
const other = { id: "m2", code: "ABC-M002", full_name: "Ravi Iyer", email: "ravi@example.local", status: "active", invite_pending: true, is_you: false };
const team = (masters: unknown[]) => ({ org: { id: "o1", name: "ABC Overseas", prefix: "ABC", status: "active" }, masters, limit: 3 });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AgentTeamPanel (AGN-001)", () => {
  it("loads, lists Masters, and hides Deactivate for the last active Master", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(team([me]))));
    render(<AgentTeamPanel />);
    expect(screen.getByText("Loading your team…")).toBeInTheDocument();
    expect(await screen.findByText("ABC-M001")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Deactivate/ })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res(team([me]))));
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ABC-M001")).toBeInTheDocument();
  });

  it("disables the invite form at the limit", async () => {
    const third = { ...other, id: "m3", code: "ABC-M003" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(team([me, other, third]))));
    render(<AgentTeamPanel />);
    expect(await screen.findByText("Limit reached: 3 active Masters. Deactivate one to invite another.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send invite" })).toBeDisabled();
  });

  it("invites and reports an undelivered email", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(team([me])))
      .mockResolvedValueOnce(res({ member: other, email_status: "not_configured" }, 201))
      .mockResolvedValueOnce(res(team([me, other])));
    vi.stubGlobal("fetch", mock);
    render(<AgentTeamPanel />);
    await screen.findByText("ABC-M001");
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Ravi Iyer" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ravi@example.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText("Invite created, but the email was not delivered. Ask Overseas Admin to re-send the link.")).toBeInTheDocument();
    expect(await screen.findByText("Invite pending")).toBeInTheDocument();
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ full_name: "Ravi Iyer", email: "ravi@example.local", phone: null });
    // The page's server-rendered Team table must pick up the new Master too (browser check, 2026-09-28).
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the server's 422 on invite", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(team([me]))).mockResolvedValueOnce(res({ detail: "This agency already has 3 active Masters" }, 422)));
    render(<AgentTeamPanel />);
    await screen.findByText("ABC-M001");
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "x@example.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText("This agency already has 3 active Masters")).toBeInTheDocument();
  });

  it("shows the invite throttle message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(team([me]))).mockResolvedValueOnce(res({ detail: "This agency has sent 10 invites in the last 24 hours. Try again later." }, 429)));
    render(<AgentTeamPanel />);
    await screen.findByText("ABC-M001");
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "x@example.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText("This agency has sent 10 invites in the last 24 hours. Try again later.")).toBeInTheDocument();
  });

  it("confirms before deactivating, ignores repeat clicks, and shows a race 422", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockResolvedValueOnce(res(team([me, other]))).mockReturnValueOnce(new Promise<Response>((r) => { release = r; }));
    vi.stubGlobal("fetch", mock);
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Ravi Iyer" }));
    const confirm = screen.getByRole("button", { name: "Confirm deactivate" });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(mock).toHaveBeenCalledTimes(2);
    release(res({ detail: "An agency must keep at least one active Master" }, 422));
    expect(await screen.findByText("An agency must keep at least one active Master")).toBeInTheDocument();
  });

  it("moves focus into the deactivate confirmation and back on Cancel (keyboard support)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(team([me, other]))));
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Ravi Iyer" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Confirm deactivate" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Deactivate Ravi Iyer" }));
  });

  it("sends a Master who deactivated themselves to the login page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(team([me, other]))).mockResolvedValueOnce(res({ member: { ...me, status: "deactivated" } })));
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Asha Rao (you)" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/login"));
  });
});
