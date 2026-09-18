import { afterEach, describe, expect, it, vi } from "vitest";

import { errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

afterEach(() => vi.unstubAllGlobals());

describe("welcomeLinkFeedback", () => {
  it("is a success for a sent link and states the 72-hour validity", () => {
    const result = welcomeLinkFeedback("Account created for a@b.co.", { email_status: "sent" });
    expect(result.tone).toBe("success");
    expect(result.text).toContain("Account created for a@b.co.");
    expect(result.text).toContain("72 hours");
  });

  it("is a warning, not an error, when email is not configured", () => {
    const result = welcomeLinkFeedback("Account created.", { email_status: "not_configured" });
    expect(result.tone).toBe("warning");
    expect(result.text).toContain("not configured");
    expect(result.text).toContain("Re-send");
  });

  it("is a warning when the send failed", () => {
    const result = welcomeLinkFeedback("Account created.", { email_status: "failed" });
    expect(result.tone).toBe("warning");
    expect(result.text).toContain("could not be sent");
  });

  it("never mentions a password value", () => {
    expect(welcomeLinkFeedback("x", { email_status: "sent" }).text).not.toMatch(/ChangeMe/);
  });
});

describe("toneClass", () => {
  it("maps tones onto the existing message classes plus form-warning", () => {
    expect(toneClass).toEqual({ success: "form-message", warning: "form-warning", error: "form-error" });
  });
});

describe("errorText", () => {
  it("uses a string detail and falls back otherwise", () => {
    expect(errorText("Nope", "fallback")).toBe("Nope");
    expect(errorText([{ msg: "x" }], "fallback")).toBe("fallback");
    expect(errorText(undefined, "fallback")).toBe("fallback");
  });
});

describe("requestWelcomeLink", () => {
  it("POSTs to the welcome-links endpoint and returns the parsed body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ email_status: "sent" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await requestWelcomeLink("u1");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/users/u1/welcome-links", { method: "POST" });
    expect(result).toEqual({ ok: true, data: { email_status: "sent" } });
  });

  it("returns ok:false with the server detail on an error status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "no pending invitation" }), { status: 409 })));
    expect(await requestWelcomeLink("u1")).toEqual({ ok: false, data: { detail: "no pending invitation" } });
  });

  it("never throws on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const result = await requestWelcomeLink("u1");
    expect(result.ok).toBe(false);
    expect(String(result.data.detail)).toContain("Network error");
  });
});
