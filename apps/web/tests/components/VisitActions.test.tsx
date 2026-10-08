import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VisitActions from "@/components/VisitActions";
import { visit } from "./visitFixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const call = (mock: ReturnType<typeof vi.fn>, i = 0) => mock.mock.calls[i] as [string, RequestInit];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("VisitActions (upc-010)", () => {
  it("shows only the actions the API allows", () => {
    render(<VisitActions visit={visit({ permissions: { ...visit().permissions, can_submit: true, can_close: true } })} />);
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close visit" })).toBeInTheDocument();
    for (const name of ["Approve", "Reject", "Mark travel booked", "Mark visit completed", "Start follow-up"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("renders nothing when no action is allowed", () => {
    const { container } = render(<VisitActions visit={visit()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("submits, announces it and refreshes", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ visit: visit() })));
    vi.stubGlobal("fetch", mock);
    render(<VisitActions visit={visit({ permissions: { ...visit().permissions, can_submit: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Submitted for approval."));
    expect(call(mock)[0]).toBe("/api/v1/partnership/visits/v1/submit");
    expect(call(mock)[1].method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
  });

  it("QA-I1: after a success the stale actions are gone until the re-read visit arrives", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ visit: visit() }))));
    const draft = visit({ permissions: { ...visit().permissions, can_submit: true, can_close: true } });
    const { rerender } = render(<VisitActions visit={draft} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Submitted for approval."));
    expect(screen.queryByRole("button", { name: "Submit for approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close visit" })).not.toBeInTheDocument();
    rerender(<VisitActions visit={visit({ approval_state: "waiting", updated_at: "2030-01-02T00:00:00Z", permissions: { ...visit().permissions, can_close: true } })} />);
    expect(screen.getByRole("button", { name: "Close visit" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Submitted for approval.");
  });

  it("a rejection needs a reason before anything is sent", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ visit: visit() })));
    vi.stubGlobal("fetch", mock);
    render(<VisitActions visit={visit({ permissions: { ...visit().permissions, can_decide: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    expect(screen.getByText("A reason is required")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason for returning the visit"), { target: { value: "Combine with Leeds" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(call(mock)[0]).toBe("/api/v1/partnership/visits/v1/reject");
    expect(JSON.parse(String(call(mock)[1].body))).toEqual({ reason: "Combine with Leeds" });
  });

  it("completing asks for the follow-up date (AC3)", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ visit: visit() })));
    vi.stubGlobal("fetch", mock);
    render(<VisitActions visit={visit({ status: "travel_booked", approval_state: null, permissions: { ...visit().permissions, can_complete: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark visit completed" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm completed" }));
    expect(screen.getByText("Choose the follow-up date")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Follow-up date"), { target: { value: "2030-01-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm completed" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(JSON.parse(String(call(mock)[1].body))).toEqual({ follow_up_date: "2030-01-15" });
  });

  it("closing before the visit happened needs a reason; after the follow-up it does not", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ visit: visit() })));
    vi.stubGlobal("fetch", mock);
    const { unmount } = render(<VisitActions visit={visit({ status: "approved", approval_state: null, permissions: { ...visit().permissions, can_close: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Close visit" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm close" }));
    expect(screen.getByText("A reason is required")).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
    unmount();
    render(<VisitActions visit={visit({ status: "follow_up", approval_state: null, permissions: { ...visit().permissions, can_close: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Close visit" }));
    expect(screen.getByLabelText("Closing note (optional)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm close" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(JSON.parse(String(call(mock)[1].body))).toEqual({});
  });

  it("shows the API's refusal as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This visit is closed and can't be booked" }, 409))));
    render(<VisitActions visit={visit({ status: "approved", approval_state: null, permissions: { ...visit().permissions, can_book: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark travel booked" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("This visit is closed and can't be booked"));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("words an unreadable server error plainly", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("oops", { status: 500 }))));
    render(<VisitActions visit={visit({ permissions: { ...visit().permissions, can_submit: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The change could not be saved. Try again."));
  });
});
