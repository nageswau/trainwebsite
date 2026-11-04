import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterOwnershipSetting from "@/components/RecruiterOwnershipSetting";

// hrc-012 (DEC-SCOPE-381 O4): the shared-ownership switch -- shown only to who may change it (managers, super_admin); saved at once.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterOwnershipSetting", () => {
  it("renders nothing for a recruiter", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ shared_ownership: false, can_edit: false })));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<RecruiterOwnershipSetting />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("lets a manager switch shared ownership on, and says so", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(res(init?.method === "PUT" ? { shared_ownership: true, can_edit: true } : { shared_ownership: false, can_edit: true })));
    vi.stubGlobal("fetch", fetchMock);
    render(<RecruiterOwnershipSetting />);
    const box = await screen.findByRole("checkbox", { name: /Allow collaborators/ });
    expect(box).not.toBeChecked();
    fireEvent.click(box);
    await waitFor(() => expect(box).toBeChecked());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ shared_ownership: true });
    expect(screen.getByRole("status")).toHaveTextContent("Collaborators can now be added to candidates.");
  });

  it("puts the box back and explains when saving fails", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PUT" ? res({ detail: "nope" }, 500) : res({ shared_ownership: true, can_edit: true }))));
    render(<RecruiterOwnershipSetting />);
    const box = await screen.findByRole("checkbox", { name: /Allow collaborators/ });
    fireEvent.click(box);
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save the setting. Please try again.");
    expect(box).toBeChecked();
  });
});
