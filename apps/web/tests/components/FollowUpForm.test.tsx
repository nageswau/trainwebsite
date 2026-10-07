import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FollowUpForm from "@/components/FollowUpForm";
import { followUp } from "@/tests/helpers/followUps";

// tel-011 (spec §4, F5/F6): add or reschedule a follow-up -- the §7 fields, the optional stage move, and the API's rules placed on fields.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

let fetchMock: ReturnType<typeof vi.fn>;
let reply: () => Response;
const sent = () => {
  const [url, init] = fetchMock.mock.calls[0];
  return { url: String(url), method: init.method, body: JSON.parse(String(init.body)) };
};
beforeEach(() => {
  reply = () => res(followUp());
  fetchMock = vi.fn(() => Promise.resolve(reply()));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const fill = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("FollowUpForm (tel-011)", () => {
  it("requires a due time and a reason before sending", async () => {
    render(<FollowUpForm leadId="L1" leadStage="contacted" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    expect(await screen.findByText("Choose a due date and time")).toBeTruthy();
    expect(screen.getByText("Choose a reason")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates with the IST time, the reason, trimmed text and the stage tick", async () => {
    const onSaved = vi.fn();
    render(<FollowUpForm leadId="L1" leadStage="contacted" onSaved={onSaved} onCancel={vi.fn()} />);
    fill(/Due date and time/, "2026-10-08T16:00");
    fill("Reason (required)", "discuss_with_parents");
    fill("Next action", "  Call today at 4:00 PM ");
    fireEvent.click(screen.getByLabelText("Also move the lead to Follow-up"));
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent()).toEqual({
      url: "/api/v1/telecaller/leads/L1/follow-ups", method: "POST",
      body: { due_at: "2026-10-08T16:00:00+05:30", reason: "discuss_with_parents", notes: null, next_action: "Call today at 4:00 PM", move_to_follow_up: true },
    });
  });

  it("does not offer the stage tick where the move is not allowed", () => {
    render(<FollowUpForm leadId="L1" leadStage="follow_up" onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Also move the lead to Follow-up")).toBeNull();
  });

  it("puts the API's time rule on the field and keeps the typed text", async () => {
    reply = () => res({ detail: [{ loc: ["body", "due_at"], msg: "Choose a due time in the future", type: "value_error" }] }, 422);
    render(<FollowUpForm leadId="L1" leadStage="contacted" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fill(/Due date and time/, "2026-10-01T09:00");
    fill("Reason (required)", "fee_details");
    fill("Notes", "Keep me");
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    expect(await screen.findByText("Choose a due time in the future")).toBeTruthy();
    expect(screen.getByLabelText(/Due date and time/).getAttribute("aria-invalid")).toBe("true");
    expect((screen.getByLabelText("Notes") as HTMLTextAreaElement).value).toBe("Keep me");
  });

  it("shows a refusal such as a closed lead in its own words", async () => {
    reply = () => res({ detail: "This lead is closed. A manager can reopen it before a follow-up is added" }, 409);
    render(<FollowUpForm leadId="L1" leadStage="contacted" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fill(/Due date and time/, "2026-10-08T16:00");
    fill("Reason (required)", "fee_details");
    fireEvent.click(screen.getByRole("button", { name: "Add follow-up" }));
    expect((await screen.findByRole("alert")).textContent).toContain("This lead is closed");
  });

  it("reschedules by sending only what changed", async () => {
    const onSaved = vi.fn();
    render(<FollowUpForm leadId="L1" leadStage="contacted" followUp={followUp()} onSaved={onSaved} onCancel={vi.fn()} />);
    expect((screen.getByLabelText(/Due date and time/) as HTMLInputElement).value).toBe("2026-10-08T16:00"); // 10:30Z in IST
    expect(screen.queryByLabelText("Also move the lead to Follow-up")).toBeNull();
    fill(/Due date and time/, "2026-10-09T11:15");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent()).toEqual({ url: "/api/v1/telecaller/follow-ups/F1", method: "PATCH", body: { due_at: "2026-10-09T11:15:00+05:30" } });
  });

  it("closes without a request when nothing changed", () => {
    const onCancel = vi.fn();
    render(<FollowUpForm leadId="L1" leadStage="contacted" followUp={followUp()} onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onCancel).toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
