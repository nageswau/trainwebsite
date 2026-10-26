import { describe, expect, it } from "vitest";
import { COURSE_ICONS, courseIconKey, ICON_LABELS } from "@/lib/courseIcons";

describe("courseIconKey (nehn-036 I5)", () => {
  it.each([
    ["Computer Science", "computing"],
    ["Software Engineering", "computing"],
    ["Informatics", "computing"],
    ["Data Science", "data"],
    ["Business Analytics", "data"],
    ["Artificial Intelligence", "ai"],
    ["AI and Robotics", "ai"],
    ["Machine Learning", "ai"],
    ["Cyber Security", "security"],
    ["Mechanical Engineering", "engineering"],
    ["Business", "business"],
    ["MBA", "business"],
    ["Management", "business"],
    ["Nursing", "health"],
    ["Public Health", "health"],
    ["Hospitality", "hospitality"],
    ["Tourism Management", "hospitality"],
    ["Law", "law"],
    ["Education", "education"],
    ["Graphic Design", "arts"],
    ["Fine Art", "arts"],
    ["Physics", "science"],
    ["Life Sciences", "science"],
  ])("derives %s as %s", (category, key) => {
    expect(courseIconKey(null, category)).toBe(key);
  });

  it("gives an unknown or blank category the general icon", () => {
    expect(courseIconKey(null, "Masters")).toBe("general");
    expect(courseIconKey(null, "")).toBe("general");
    expect(courseIconKey(undefined, "Lawn care partners")).toBe("general"); // word boundaries: "lawn" is not law
  });

  it("lets a chosen icon win over the category", () => {
    expect(courseIconKey("law", "Computer Science")).toBe("law");
  });

  it("ignores a key outside the set (falls back to the category)", () => {
    expect(courseIconKey("rocket", "Computer Science")).toBe("computing");
  });

  it("labels every key in the API's order", () => {
    expect(COURSE_ICONS).toEqual(["ai", "security", "data", "computing", "engineering", "business", "health", "hospitality", "law", "education", "arts", "science", "general"]);
    expect(Object.keys(ICON_LABELS).sort()).toEqual([...COURSE_ICONS].sort());
  });
});
