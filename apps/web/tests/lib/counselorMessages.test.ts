import { describe, expect, it } from "vitest";

import { COUNSELOR_LIBRARY, replyUrl, studentMessagesUrl, studentTarget } from "@/lib/counselorMessages";

// ccrm-037 (DEC-SCOPE-273): the counselor's endpoints -- the application the message is about rides on the render query and the send body.
describe("counselorMessages (ccrm-037)", () => {
  it("builds the student's list and reply URLs", () => {
    expect(studentMessagesUrl("S 1")).toBe("/api/v1/counselor/students/S%201/messages?limit=50");
    expect(replyUrl("S1")).toBe("/api/v1/counselor/students/S1/replies");
  });

  it("targets a general message without an application", () => {
    const target = studentTarget("S1", "");
    expect(target.renderUrl("T1")).toBe("/api/v1/counselor/students/S1/messages/render?template_id=T1");
    expect(target.createUrl).toBe("/api/v1/counselor/students/S1/messages");
    expect(target.payload).toEqual({});
  });

  it("targets a message about one application", () => {
    const target = studentTarget("S1", "A1");
    expect(target.renderUrl("T1")).toBe("/api/v1/counselor/students/S1/messages/render?template_id=T1&application_id=A1");
    expect(target.payload).toEqual({ application_id: "A1" });
  });

  it("names the merge fields the API accepts (MT2)", () => {
    expect(COUNSELOR_LIBRARY.url).toBe("/api/v1/counselor/templates");
    expect(COUNSELOR_LIBRARY.kinds).toBeNull();
    expect(COUNSELOR_LIBRARY.placeholders).toEqual(["name", "university", "course", "intake", "application_deadline", "offer_deadline", "counselor"]);
  });
});
