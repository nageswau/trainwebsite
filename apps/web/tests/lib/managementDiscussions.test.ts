import { describe, expect, it } from "vitest";

import { decisionLine, discussionFilters, discussionsHref, discussionsUrl, isOverdue, PENDING_URL } from "@/lib/managementDiscussions";

describe("mgmt-027 discussion filters and links", () => {
  it("keeps a known status and a positive offset, drops anything hand-edited", () => {
    expect(discussionFilters({ status: "in_progress", offset: "25" })).toEqual({ status: "in_progress", offset: 25 });
    expect(discussionFilters({ status: "done", offset: "-4" })).toEqual({ status: "", offset: 0 });
    expect(discussionFilters({ status: ["open", "completed"], offset: "99999" })).toEqual({ status: "", offset: 0 });
  });

  it("builds the page link and the API URL", () => {
    expect(discussionsHref({ status: "", offset: 0 })).toBe("/management/discussions");
    expect(discussionsHref({ status: "open", offset: 25 })).toBe("/management/discussions?status=open&offset=25");
    expect(discussionsUrl({ status: "open", offset: 0 })).toBe("/api/v1/management/discussions?status=open&limit=25");
    expect(PENDING_URL).toBe("/api/v1/management/discussions?pending=true&limit=10");
  });
});

describe("mgmt-027 decision line", () => {
  it("reads like the source example", () => {
    expect(decisionLine({ decision: "Proceed with agreement", deadline: "2026-10-10", status: "in_progress" })).toBe("Proceed with agreement — 10 Oct 2026 — In Progress");
    expect(decisionLine({ decision: "Hire a trainer", deadline: null, status: "open" })).toBe("Hire a trainer — no deadline — Open");
  });

  it("flags an unfinished decision past its deadline (India date)", () => {
    expect(isOverdue({ deadline: "2026-10-09", status: "open" }, "2026-10-10")).toBe(true);
    expect(isOverdue({ deadline: "2026-10-10", status: "in_progress" }, "2026-10-10")).toBe(false);
    expect(isOverdue({ deadline: "2026-10-01", status: "completed" }, "2026-10-10")).toBe(false);
    expect(isOverdue({ deadline: null, status: "open" }, "2026-10-10")).toBe(false);
  });
});
