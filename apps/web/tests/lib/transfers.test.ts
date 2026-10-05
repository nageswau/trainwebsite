import { describe, expect, it } from "vitest";

import { detailMessage, isPage, isRequestBody } from "@/lib/apiErrors";
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

  it("drops Pydantic's \"Value error, \" prefix from a 422 and starts the sentence with a capital (browser QA N1)", () => {
    expect(detailMessage([{ msg: "Value error, must be 500 characters or fewer" }])).toBe("Must be 500 characters or fewer");
    expect(detailMessage([{ msg: "Value error, must not contain control or bidirectional-override characters" }, { msg: "Field required" }])).toBe(
      "Must not contain control or bidirectional-override characters; Field required",
    );
  });

  it("leaves a string detail alone even when it happens to start the same way", () => {
    expect(detailMessage("Value error, kept as the server wrote it")).toBe("Value error, kept as the server wrote it");
  });
});

describe("isRequestBody", () => {
  it("accepts the body of a filed, cancelled or decided request", () => {
    expect(isRequestBody({ id: "r1", status: "pending" })).toBe(true);
    expect(isRequestBody({ id: "r1" })).toBe(true);
  });

  it("rejects what a proxy or an empty body produces, so a 200 is never taken for a success (browser QA N2)", () => {
    for (const bad of [null, undefined, "<html>", [], {}, { id: 1 }, { accepted: true }]) {
      expect(isRequestBody(bad)).toBe(false);
    }
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
