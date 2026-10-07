import { describe, expect, it } from "vitest";

import { isRenderedTemplate, leadMessagesUrl, renderUrl, sentLabel, waHref } from "@/lib/telecallerMessages";

// tel-013 (DEC-SCOPE-099): wa.me links, the "WhatsApp sent" line and the endpoints.
describe("telecallerMessages (tel-013)", () => {
  it("builds a wa.me link with the number's digits and the URL-encoded text", () => {
    expect(waHref("919876543210", "Hi Priya & co?\nLink: https://x.test/a?b=1#c"))
      .toBe("https://wa.me/919876543210?text=Hi%20Priya%20%26%20co%3F%0ALink%3A%20https%3A%2F%2Fx.test%2Fa%3Fb%3D1%23c");
    expect(waHref("447700900123", "")).toBe("https://wa.me/447700900123");
  });

  it("reads a send as the source's 'WhatsApp sent – date – time' in India time (AC2)", () => {
    expect(sentLabel("2026-09-13T05:05:00Z")).toBe("WhatsApp sent – 13 Sept 2026 – 10:35 AM");
    expect(sentLabel("2026-09-13T12:30:00Z")).toBe("WhatsApp sent – 13 Sept 2026 – 6:00 PM");
  });

  it("knows the endpoints and recognises a rendered template", () => {
    expect(leadMessagesUrl("L 1")).toBe("/api/v1/telecaller/leads/L%201/messages?limit=50");
    expect(renderUrl("L1", "T1")).toBe("/api/v1/telecaller/leads/L1/render?template_id=T1");
    expect(isRenderedTemplate({ body: "Hi", product_mismatch: false })).toBe(true);
    expect(isRenderedTemplate({ detail: "Template not found" })).toBe(false);
  });
});
