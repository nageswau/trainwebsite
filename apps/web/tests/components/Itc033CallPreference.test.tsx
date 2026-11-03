import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";
import { isNotificationPreferences } from "@/lib/types";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const prefs = { whatsapp: false, sms: false, calls: true, phone_valid: false };
const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });
const callsBox = () => screen.getByRole("checkbox", { name: /^Phone calls from our team/ });

describe("itc-033 phone-call preference (DEC-SCOPE-357 C1/C2)", () => {
  it("shows calls as allowed by default and changeable without a valid phone", () => {
    render(<NotificationPreferencesForm initial={prefs} phone={null} />);
    expect(callsBox()).toBeChecked();
    expect(callsBox()).toBeEnabled();
    expect(callsBox()).not.toHaveAttribute("aria-describedby", "notification-phone-hint");
  });

  it("saves calls off together with the messaging channels", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ ...prefs, calls: false }));
    render(<NotificationPreferencesForm initial={prefs} phone={null} />);
    fireEvent.click(callsBox());
    fireEvent.click(screen.getByRole("button", { name: "Save notification settings" }));
    expect(await screen.findByText("Notification settings saved.")).toBeInTheDocument();
    expect(JSON.parse(vi.mocked(global.fetch).mock.calls[0][1]?.body as string)).toEqual({ whatsapp: false, sms: false, calls: false });
    expect(callsBox()).not.toBeChecked();
  });

  it("reverts the calls box when the save fails", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response("{}", { status: 500 }));
    render(<NotificationPreferencesForm initial={prefs} phone={null} />);
    fireEvent.click(callsBox());
    fireEvent.click(screen.getByRole("button", { name: "Save notification settings" }));
    expect(await screen.findByText(/Couldn't save your settings/)).toBeInTheDocument();
    expect(callsBox()).toBeChecked();
  });

  it("the type guard requires the calls flag", () => {
    expect(isNotificationPreferences(prefs)).toBe(true);
    expect(isNotificationPreferences({ whatsapp: false, sms: false, phone_valid: true })).toBe(false);
  });
});
