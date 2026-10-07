import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LeadAppointmentsSection from "@/components/LeadAppointmentsSection";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadAppointmentsSection (tel-016)", () => {
  it("re-reads the appointments when the lead closes, so a cancelled booking shows at once (AP15)", async () => {
    const fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 })));
    vi.stubGlobal("fetch", fetch);
    const { rerender } = render(<LeadAppointmentsSection leadId="l1" stage="counselling_scheduled" canBook onStage={() => {}} />);
    expect(await screen.findByText("No counselling appointments yet.")).toBeTruthy();
    rerender(<LeadAppointmentsSection leadId="l1" stage="interested" canBook onStage={() => {}} />); // an open move: no re-read
    rerender(<LeadAppointmentsSection leadId="l1" stage="lost" canBook onStage={() => {}} />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText("This lead is closed. A manager can reopen it before a booking.")).toBeTruthy();
  });
});
