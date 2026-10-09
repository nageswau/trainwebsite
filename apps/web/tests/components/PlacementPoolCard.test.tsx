import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PlacementPoolCard from "@/components/PlacementPoolCard";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const consent = { version: "v1", text: "I agree that EduSphere may add my name to its placement candidate pool." };
const out = { opted_in: false, consent, history: [] };
const joined = { opted_in: true, consent, history: [{ action: "opt_in", consent_version: "v1", created_at: "2026-10-09T10:00:00Z" }] };
const left = { opted_in: false, consent, history: [{ action: "opt_out", consent_version: "v1", created_at: "2026-10-09T11:00:00Z" }, ...joined.history] };
const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });
const fail = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });

describe("PlacementPoolCard (rec-010)", () => {
  it("shows a loading state, then the consent text and version", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(out));
    render(<PlacementPoolCard />);
    expect(screen.getByText("Loading your placement pool status…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Join the placement candidate pool" })).toBeInTheDocument();
    expect(screen.getByText(consent.text)).toBeInTheDocument();
    expect(screen.getByText("Version v1")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe("/api/v1/account/placement-pool");
  });

  it("keeps Join disabled until the consent box is ticked, then posts the version it showed", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(out)).mockResolvedValueOnce(ok(joined));
    render(<PlacementPoolCard />);
    const join = await screen.findByRole("button", { name: "Join the pool" });
    expect(join).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "I agree to the consent text above" }));
    expect(join).toBeEnabled();
    fireEvent.click(join);
    expect(await screen.findByText("You have joined the placement candidate pool.")).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[1];
    expect(url).toBe("/api/v1/account/placement-pool/opt-in");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ consent_version: "v1" });
    expect(screen.getByText("In the placement pool")).toBeInTheDocument();
    expect(screen.getByText(/Joined · /)).toBeInTheDocument();
  });

  it("ignores a second click while joining", async () => {
    let resolve: (r: Response) => void = () => undefined;
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(ok(out))
      .mockReturnValueOnce(new Promise((r) => (resolve = r)));
    render(<PlacementPoolCard />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "I agree to the consent text above" }));
    const join = screen.getByRole("button", { name: "Join the pool" });
    fireEvent.click(join);
    fireEvent.click(join);
    expect(screen.getByRole("button", { name: "Joining…" })).toBeDisabled();
    resolve(ok(joined));
    await screen.findByText("In the placement pool");
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("asks before leaving, can cancel, and leaving shows the history", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(joined)).mockResolvedValueOnce(ok(left));
    render(<PlacementPoolCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Leave the pool" }));
    expect(screen.getByText("Leave the pool? Employers will no longer find you; your applications continue.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(global.fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Leave the pool" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, leave" }));
    expect(await screen.findByText("You have left the placement candidate pool.")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[1][0]).toBe("/api/v1/account/placement-pool/opt-out");
    expect(screen.getByRole("heading", { name: "Join the placement candidate pool" })).toBeInTheDocument();
    expect(screen.getByText(/Left · /)).toBeInTheDocument();
  });

  it("shows the server's message when joining fails and keeps the student out", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(out)).mockResolvedValueOnce(fail(409, "The consent wording has changed. Review it and try again."));
    render(<PlacementPoolCard />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "I agree to the consent text above" }));
    fireEvent.click(screen.getByRole("button", { name: "Join the pool" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The consent wording has changed. Review it and try again.");
    expect(screen.queryByText("In the placement pool")).not.toBeInTheDocument();
  });

  it("shows an error with Retry when the status cannot be loaded", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(ok(out));
    render(<PlacementPoolCard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your placement pool status.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Join the placement candidate pool" })).toBeInTheDocument());
  });
});
