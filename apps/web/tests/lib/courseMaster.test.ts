import { describe, expect, it } from "vitest";

import { commissionText, coursePageHref, courseListQuery, coursesUrl, englishText, moneyText, scoreProblem } from "@/lib/courseMaster";

describe("courseMaster (upc-017)", () => {
  it("builds the university's course URLs", () => {
    expect(coursesUrl("u1")).toBe("/api/v1/partnership/universities/u1/courses");
    expect(coursesUrl("u1", "c1")).toBe("/api/v1/partnership/universities/u1/courses/c1");
  });

  it("writes money with its currency and no needless decimals", () => {
    expect(moneyText("18000.00", "GBP")).toBe("GBP 18,000");
    expect(moneyText("75.50", "GBP")).toBe("GBP 75.50");
    expect(moneyText(null, null)).toBeNull();
  });

  it("writes the one commission rate a course carries (CO2)", () => {
    expect(commissionText({ percent: "12.50", amount: null, currency: null })).toBe("12.5%");
    expect(commissionText({ percent: null, amount: "1500.00", currency: "GBP" })).toBe("GBP 1,500");
    expect(commissionText(null)).toBe("Not recorded");
  });

  it("writes the English requirement (CO8)", () => {
    expect(englishText({ english_test: "IELTS", english_score: "6.5" })).toBe("IELTS 6.5");
    expect(englishText({ english_test: "Duolingo", english_score: null })).toBe("Duolingo");
    expect(englishText({ english_test: null, english_score: null })).toBeNull();
  });

  it("checks a score against its test's scale", () => {
    expect(scoreProblem("IELTS", "6.5")).toBeNull();
    expect(scoreProblem("IELTS", "9.5")).toBe("The IELTS score cannot be above 9.");
    expect(scoreProblem("", "6.5")).toBe("Choose the English test the score is for.");
    expect(scoreProblem("TOEFL", "0")).toBe("The English score must be more than 0.");
    expect(scoreProblem("PTE", "")).toBeNull();
  });

  it("keeps only the menu's filters in its URLs", () => {
    expect(courseListQuery({ q: " cyber ", level: "PG", status: "", offset: "50" }, 50, 50)).toBe("q=cyber&level=PG&limit=50&offset=50");
    expect(coursePageHref({ status: "inactive" }, 0)).toBe("/partnership/courses?status=inactive");
    expect(coursePageHref({}, 50)).toBe("/partnership/courses?offset=50");
  });
});
