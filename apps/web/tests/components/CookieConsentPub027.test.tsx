import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CookieConsent from "@/components/CookieConsent";
import CookieSettingsButton from "@/components/CookieSettingsButton";
import { CONSENT_COOKIE, readConsent } from "@/lib/cookieConsent";

// PUB-027 (DEC-SCOPE-443): no Google Analytics before consent; Accept/Reject equal; the choice is remembered and can be changed.
vi.mock("next/script", () => ({
  default: ({ src, id }: { src?: string; id?: string }) => <span data-testid="script" data-script={src ?? id} />,
}));

const GA = "G-TEST123";

function clearCookies() {
  for (const name of document.cookie.split("; ").map((part) => part.split("=")[0]).filter(Boolean)) {
    document.cookie = `${name}=; Max-Age=0; Path=/`;
  }
}

const banner = () => screen.queryByRole("region", { name: "Cookie consent" });
const scripts = () => screen.queryAllByTestId("script").map((el) => el.getAttribute("data-script"));

beforeEach(clearCookies);
afterEach(() => {
  cleanup();
  clearCookies();
});

describe("cookie consent (PUB-027)", () => {
  it("asks a first-time visitor and loads no analytics until they choose", () => {
    render(<CookieConsent gaId={GA} />);
    expect(banner()).toBeTruthy();
    expect(scripts()).toEqual([]);
    expect(screen.getByRole("link", { name: "Read our cookie policy" }).getAttribute("href")).toBe("/privacy#cookies");
  });

  it("gives Accept and Reject the same prominence", () => {
    render(<CookieConsent gaId={GA} />);
    const accept = screen.getByRole("button", { name: "Accept analytics" });
    const reject = screen.getByRole("button", { name: "Reject analytics" });
    expect(accept.className).toBe(reject.className);
  });

  it("loads Google Analytics after Accept and remembers the choice", () => {
    render(<CookieConsent gaId={GA} />);
    fireEvent.click(screen.getByRole("button", { name: "Accept analytics" }));
    expect(banner()).toBeNull();
    expect(scripts()).toEqual([`https://www.googletagmanager.com/gtag/js?id=${GA}`, "ga"]);
    expect(readConsent()).toBe("granted");
    cleanup();
    render(<CookieConsent gaId={GA} />);
    expect(banner()).toBeNull();
    expect(scripts()).toHaveLength(2);
  });

  it("keeps analytics off after Reject, and does not ask again", () => {
    render(<CookieConsent gaId={GA} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject analytics" }));
    expect(banner()).toBeNull();
    expect(scripts()).toEqual([]);
    expect(document.cookie).toContain(`${CONSENT_COOKIE}=denied`);
    cleanup();
    render(<CookieConsent gaId={GA} />);
    expect(banner()).toBeNull();
  });

  it("Cookie settings reopens the banner; withdrawing deletes the GA cookies and sets Google's opt-out flag", () => {
    document.cookie = `${CONSENT_COOKIE}=granted; Path=/`;
    document.cookie = "_ga=GA1.1.123; Path=/";
    document.cookie = "_ga_TEST123=GS1.1.456; Path=/";
    render(<><CookieConsent gaId={GA} /><CookieSettingsButton /></>);
    expect(banner()).toBeNull();
    expect((window as unknown as Record<string, boolean>)[`ga-disable-${GA}`]).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Cookie settings" }));
    expect(banner()).toBeTruthy();
    act(() => fireEvent.click(screen.getByRole("button", { name: "Reject analytics" })));
    expect(document.cookie).not.toMatch(/_ga/);
    expect(scripts()).toEqual([]);
    expect((window as unknown as Record<string, boolean>)[`ga-disable-${GA}`]).toBe(true);
  });

  it("renders nothing when Google Analytics is not configured (no non-essential cookie to ask about)", () => {
    const { container } = render(<CookieConsent gaId={undefined} />);
    expect(container.innerHTML).toBe("");
  });
});
