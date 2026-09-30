import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const off = { whatsapp: false, sms: false, phone_valid: true };
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save notification settings" }));
const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });

describe("NotificationPreferencesForm (ENH-014)", () => {
  it("shows email and in-app as always on and not changeable", () => {
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    for (const name of ["Email", "In-app"]) {
      const box = screen.getByRole("checkbox", { name: new RegExp(`^${name}`) });
      expect(box).toBeChecked();
      expect(box).toBeDisabled();
    }
    expect(screen.getAllByText("Always on")).toHaveLength(2);
    expect(screen.getByText("Messages go to +91 98765 43210")).toBeInTheDocument();
  });

  it("disables turning WhatsApp or SMS on without a valid phone and explains why", () => {
    render(<NotificationPreferencesForm initial={{ ...off, phone_valid: false }} phone={null} />);
    const whatsapp = screen.getByRole("checkbox", { name: /^WhatsApp/ });
    expect(whatsapp).toBeDisabled();
    expect(whatsapp).toHaveAttribute("aria-describedby", "notification-phone-hint");
    expect(screen.getByRole("link", { name: "Add a mobile number" })).toHaveAttribute("href", "#profile-phone");
  });

  it("keeps a checked channel enabled so it can be turned off without a phone", () => {
    render(<NotificationPreferencesForm initial={{ whatsapp: true, sms: false, phone_valid: false }} phone={null} />);
    expect(screen.getByRole("checkbox", { name: /^WhatsApp/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: /^SMS/ })).toBeDisabled();
  });

  it("PUTs exactly the two booleans and announces success", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ whatsapp: true, sms: false, phone_valid: true }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    fireEvent.click(screen.getByRole("checkbox", { name: /^WhatsApp/ }));
    save();
    expect(await screen.findByText("Notification settings saved.")).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe("/api/v1/account/notification-preferences");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({ whatsapp: true, sms: false });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save notification settings" })).toHaveFocus());
  });

  it("ignores a second submit while saving and marks the form busy", async () => {
    let resolve: (r: Response) => void = () => undefined;
    vi.mocked(global.fetch).mockReturnValue(new Promise((r) => (resolve = r)));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    save();
    fireEvent.click(screen.getByRole("button", { name: "Saving…" }));
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("form", { name: "Notification settings" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Saving…" })).toHaveAttribute("aria-disabled", "true");
    resolve(ok(off));
    await screen.findByText("Notification settings saved.");
  });

  it("shows the server's 422 message and reverts the checkboxes", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Add a valid mobile number to your profile first" }), { status: 422 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    const sms = screen.getByRole("checkbox", { name: /^SMS/ });
    fireEvent.click(sms);
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a valid mobile number to your profile first");
    expect(sms).not.toBeChecked();
  });

  it("shows a retryable message on a network error or a 5xx and reverts", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(new Response("oops", { status: 500 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    const whatsapp = screen.getByRole("checkbox", { name: /^WhatsApp/ });
    for (let i = 0; i < 2; i += 1) {
      fireEvent.click(whatsapp);
      save();
      expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save your settings. Check your connection and try again.");
      await waitFor(() => expect(whatsapp).not.toBeChecked());
    }
  });

  it("shows the session-expired block on 401", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response("{}", { status: 401 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    save();
    expect(await screen.findByText("Your session has expired. Sign in again to change your notification settings.")).toBeInTheDocument();
  });
});
