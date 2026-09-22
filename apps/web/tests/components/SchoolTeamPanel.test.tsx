import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTeamPanel from "@/components/SchoolTeamPanel";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const ACCOUNT = { id: "11111111-1111-1111-1111-111111111111", name: "Test Teacher", email: "teacher@example.local", role: "school_teacher", active: true };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolTeamPanel (ENH010-QA-01)", () => {
  it("ignores repeat clicks on the same row while the first toggle is still pending", async () => {
    let release!: (response: Response) => void;
    const mock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", mock);

    render(<SchoolTeamPanel accounts={[ACCOUNT]} pendingInvites={[]} />);
    const button = screen.getByRole("button", { name: "Deactivate" });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mock).toHaveBeenCalledTimes(1);
    release(new Response(JSON.stringify({ id: ACCOUNT.id, active: false }), { status: 200 }));
    await screen.findByText(/deactivated\./);
  });
});
