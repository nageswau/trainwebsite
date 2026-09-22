import { afterEach, describe, expect, it, vi } from "vitest";

import { NOT_COMPLETED } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import { ENROLMENT_CLASS, ENROLMENT_LABEL, ENROLMENT_STATUSES, MODULE_LABEL, SERVER_FAILED, TRANSITIONS, attendanceText, canMark, send, type SkillEnrollment } from "@/lib/skills";

afterEach(() => vi.unstubAllGlobals());

describe("send", () => {
  const reply = (body: unknown, status = 200) => vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))));

  it("returns the body of a 2xx and sends JSON", async () => {
    reply({ id: "b1" }, 201);
    expect(await send("/x", "POST", { a: 1 })).toEqual({ ok: true, data: { id: "b1" } });
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init).toMatchObject({ method: "POST", body: '{"a":1}', headers: { "Content-Type": "application/json" } });
  });

  it("maps a 422 list to a message and per-field errors", async () => {
    reply({ detail: [{ loc: ["body", "title"], msg: "Value error, must not be blank" }, { loc: ["body", "end_date"], msg: "Input should be a valid date" }] }, 422);
    const result = await send("/x", "POST", {});
    expect(result).toEqual({ ok: false, message: "Must not be blank; Input should be a valid date", fields: { title: "Must not be blank", end_date: "Input should be a valid date" } });
  });

  it("shows a string detail as written, flags an expired session, and keeps the entry on a network failure", async () => {
    reply({ detail: "This batch is closed. Reopen it to make this change." }, 409);
    expect(await send("/x", "PUT", {})).toEqual({ ok: false, message: "This batch is closed. Reopen it to make this change.", fields: {} });
    reply({ detail: "Not authenticated" }, 401);
    expect(await send("/x", "GET")).toMatchObject({ ok: false, expired: true });
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    expect(await send("/x", "GET")).toEqual({ ok: false, message: NOT_COMPLETED, fields: {} });
  });

  it("says a server failure did not save anything, and that the entry is kept (QA-10)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("Internal Server Error", { status: 500 }))));
    expect(await send("/x", "PUT", {})).toEqual({ ok: false, message: SERVER_FAILED, fields: {} });
    expect(SERVER_FAILED).toBe("The change was not saved because of a problem on our side. Your entry is kept; please try again in a moment.");
  });

  it("does not report success for a 2xx without a JSON body", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("<html>login</html>", { status: 200 }))));
    expect(await send("/x", "GET")).toMatchObject({ ok: false, fields: {} });
  });
});

// ENH-011 (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5.1, §7): the shared labels and rules the
// counselor screens use. TRANSITIONS must equal the API's table exactly, so the UI never offers a change the API refuses.

function enrolment(over: Partial<SkillEnrollment> = {}): SkillEnrollment {
  return {
    id: "e1", batch_id: "b1", school_student_id: "s1", student_name: "Asha R", status: "enrolled", frozen: false,
    completed_at: null, certified_at: null, created_at: "2026-10-01T10:00:00Z", attendance: { present: 0, marked: 0 }, scores: [], ...over,
  };
}

describe("lib/skills", () => {
  it("labels every module and enrolment status in words, with a class", () => {
    expect(MODULE_LABEL).toEqual({ soft_skills: "Soft Skills", digital_skills: "Digital Skills" });
    for (const status of ENROLMENT_STATUSES) {
      expect(ENROLMENT_LABEL[status]).toMatch(/\w/);
      expect(typeof ENROLMENT_CLASS[status]).toBe("string");
    }
  });

  it("mirrors the API's transition table, with certified terminal", () => {
    expect(TRANSITIONS).toEqual({
      enrolled: ["completed", "certified", "withdrawn"],
      completed: ["certified", "enrolled"],
      withdrawn: ["enrolled"],
      certified: [],
    });
  });

  it("describes attendance in words", () => {
    expect(attendanceText({ present: 0, marked: 0 })).toBe("No attendance yet");
    expect(attendanceText({ present: 4, marked: 5 })).toBe("Attended 4 of 5 sessions");
    expect(attendanceText({ present: 1, marked: 1 })).toBe("Attended 1 of 1 session");
  });

  it("only enrolled or completed, not-frozen enrolments take attendance and scores", () => {
    expect(canMark(enrolment())).toBe(true);
    expect(canMark(enrolment({ status: "completed" }))).toBe(true);
    expect(canMark(enrolment({ status: "certified" }))).toBe(false);
    expect(canMark(enrolment({ status: "withdrawn" }))).toBe(false);
    expect(canMark(enrolment({ frozen: true }))).toBe(false);
  });

  it("gives the career counselor a Skills entry after the dashboard", () => {
    expect(SCHOOL_NAV["career-counselor"].map((item) => [item.label, item.href])).toEqual([
      ["Dashboard", "/school/career-counselor/dashboard"],
      ["Skills", "/school/career-counselor/skills"],
    ]);
  });
});
