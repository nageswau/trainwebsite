import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorChatPanel from "@/components/CounselorChatPanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stub() {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/lookups/overseas-students?")) return Promise.resolve(json({ items: [{ id: "w1", label: "Walk In", detail: "walk@example.local" }], truncated: false }));
    if (url === "/api/v1/communications/messages/w1") return Promise.resolve(json([]));
    if (init?.method === "POST") return Promise.resolve(json({ id: "m1" }, 201));
    return Promise.resolve(json({ rows: [] }));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CounselorChatPanel (ccrm-044)", () => {
  it("picks from the counselor's caseload lookup (walk-ins included) and replies to the pick", async () => {
    const mock = stub();
    render(<CounselorChatPanel userId="c1" />);
    const input = screen.getByRole("combobox", { name: "Student" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Walk" } });
    fireEvent.click(await screen.findByRole("option", { name: "Walk In — walk@example.local" }));
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-students?limit=20&q=Walk")).toBe(true);
    expect(mock.mock.calls.some(([url]) => String(url).includes("/counselor/applications"))).toBe(false);
    fireEvent.change(await screen.findByLabelText("Reply"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reply" }));
    await waitFor(() => {
      const post = mock.mock.calls.find(([url, init]) => url === "/api/v1/communications/messages" && init?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ recipient_id: "w1", body: "Hello", context_type: "counselor_chat" });
    });
    expect(await screen.findByText("Reply sent.")).toBeTruthy();
  });

  it("shows the server's refusal when a send is not allowed", async () => {
    const mock = stub();
    mock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/lookups/")) return Promise.resolve(json({ items: [{ id: "w1", label: "Walk In" }], truncated: false }));
      if (init?.method === "POST") return Promise.resolve(json({ detail: "This student is not one of your students" }, 403));
      return Promise.resolve(json([]));
    });
    render(<CounselorChatPanel userId="c1" />);
    const input = screen.getByRole("combobox", { name: "Student" });
    fireEvent.focus(input);
    fireEvent.click(await screen.findByRole("option", { name: "Walk In" }));
    fireEvent.change(await screen.findByLabelText("Reply"), { target: { value: "Hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reply" }));
    expect(await screen.findByText("This student is not one of your students")).toBeTruthy();
  });
});
