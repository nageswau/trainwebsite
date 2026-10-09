import { afterEach, describe, expect, it, vi } from "vitest";

import { contactTarget, COMMS_READERS, PARTNERSHIP_LIBRARY, universityCallsUrl, universityMessagesUrl } from "@/lib/partnershipComms";
import { unknownPlaceholders } from "@/lib/recruiterMessages";

afterEach(() => vi.unstubAllGlobals());

describe("upc-012 partnershipComms", () => {
  it("names the university lists and who reads them (UC3)", () => {
    expect(universityCallsUrl("u 1")).toBe("/api/v1/partnership/universities/u%201/calls?limit=50");
    expect(universityMessagesUrl("u1")).toBe("/api/v1/partnership/universities/u1/messages?limit=50");
    expect([...COMMS_READERS].sort()).toEqual(["partnership_head", "partnership_manager", "super_admin"]);
  });

  it("is a library without kinds and with its own placeholders (UC4, UC5)", () => {
    expect(PARTNERSHIP_LIBRARY.kinds).toBeNull();
    expect(PARTNERSHIP_LIBRARY.url).toBe("/api/v1/partnership/templates");
    expect(unknownPlaceholders("Dear {name} at {university}, {manager} {company}", PARTNERSHIP_LIBRARY.placeholders)).toEqual(["{company}"]);
  });

  it("targets one contact: the render query and the send body carry its id", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: "t1", name: "Proposal" }], total: 1, limit: 100, offset: 0 }))));
    vi.stubGlobal("fetch", fetchMock);
    const target = contactTarget("c1");
    expect(target.renderUrl("t 1")).toBe("/api/v1/partnership/messages/render?template_id=t%201&contact_id=c1");
    expect(target.createUrl).toBe("/api/v1/partnership/messages");
    expect(target.payload).toEqual({ contact_id: "c1" });
    expect(await target.loadTemplates("email")).toEqual([{ id: "t1", name: "Proposal" }]);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/^\/api\/v1\/partnership\/templates\?channel=email&active=true/);
  });
});
