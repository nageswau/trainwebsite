import { describe, expect, it } from "vitest";

import { detailMessage, isPage } from "@/lib/apiErrors";
import { STATUS_CLASS, STATUS_LABEL, type TransferStatus } from "@/lib/transfers";

// ENH-005 frontend foundation (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §7.1).

describe("detailMessage", () => {
  it("returns a string detail as is (403/409/429)", () => {
    expect(detailMessage("This transfer request has already been decided")).toBe("This transfer request has already been decided");
  });

  it("joins FastAPI's 422 list into one sentence", () => {
    expect(detailMessage([{ msg: "Field required" }, { msg: "Invalid input" }, {}])).toBe("Field required; Invalid input; Invalid input");
  });

  it("falls back for anything unreadable", () => {
    expect(detailMessage(undefined)).toBe("Something went wrong.");
    expect(detailMessage({ nope: 1 }, "Custom")).toBe("Custom");
  });
});

describe("isPage", () => {
  it("accepts the limit/offset envelope", () => {
    expect(isPage({ items: [], total: 0, limit: 25, offset: 0 })).toBe(true);
  });

  it("rejects a login page, an empty body, or a bare array so a 200 can never crash the screen", () => {
    for (const bad of [null, undefined, "<html>", [], {}, { items: "x", total: 1, limit: 1, offset: 0 }, { items: [], total: "1", limit: 1, offset: 0 }]) {
      expect(isPage(bad)).toBe(false);
    }
  });
});

describe("status presentation", () => {
  it("has a text label and a class for every status, never colour alone", () => {
    const statuses: TransferStatus[] = ["pending", "approved", "rejected", "cancelled"];
    for (const s of statuses) {
      expect(STATUS_LABEL[s].length).toBeGreaterThan(3);
      expect(STATUS_CLASS[s]).toContain("status");
    }
    expect(STATUS_LABEL.pending).toBe("Pending review");
    expect(STATUS_CLASS.rejected).toContain("error");
    expect(STATUS_CLASS.pending).toContain("pending");
  });
});
