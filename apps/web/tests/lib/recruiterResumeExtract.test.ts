import { describe, expect, it } from "vitest";

import { applyBody, applyUrl, extractUrl, initialSelection, savedMessage } from "@/lib/recruiterResumeExtract";
import { extraction } from "@/tests/helpers/recruiterResumeExtract";

// rec-012 (EX6): the URLs, the default ticks (skills not on the profile; fields only where the candidate has none) and the body.
const EMPTY = { qualification: null, experience_months: null, location: null };

describe("recruiterResumeExtract (rec-012)", () => {
  it("builds the URLs", () => {
    expect(extractUrl("C 1", 2)).toBe("/api/v1/recruiter/candidates/C%201/resume/2/extract");
    expect(applyUrl("C1", 3)).toBe("/api/v1/recruiter/candidates/C1/resume/3/apply");
  });

  it("ticks the new skills at Intermediate and the fields the candidate lacks", () => {
    const selection = initialSelection(extraction(), { ...EMPTY, location: "Hyderabad" });
    expect(selection.skills).toEqual({ "K-boot": true, "K-rest": true });
    expect(selection.levels).toEqual({ "K-java": "intermediate", "K-boot": "intermediate", "K-rest": "intermediate" });
    expect(selection.fields).toEqual({ qualification: true, experience_months: true, location: false });
  });

  it("sends only the ticked skills with their levels and the ticked fields with the suggested values", () => {
    const e = extraction();
    const selection = initialSelection(e, EMPTY);
    selection.skills["K-rest"] = false;
    selection.levels["K-boot"] = "advanced";
    selection.fields.location = false;
    expect(applyBody(e, selection)).toEqual({ skills: [{ skill_id: "K-boot", level: "advanced" }], qualification: "B.Tech", experience_months: 36 });
  });

  it("never sends a skill already on the profile or a field with no suggestion", () => {
    const e = extraction({ qualification: null });
    const selection = initialSelection(e, EMPTY);
    selection.skills["K-java"] = true;
    selection.fields.qualification = true;
    const body = applyBody(e, selection);
    expect(body.skills.map((s) => s.skill_id)).toEqual(["K-boot", "K-rest"]);
    expect(body).not.toHaveProperty("qualification");
  });

  it("words what was saved", () => {
    expect(savedMessage({ skills_added: 2, fields: ["experience_months", "location"] })).toBe("Added 2 skills and updated total experience and location.");
    expect(savedMessage({ skills_added: 1, fields: [] })).toBe("Added 1 skill.");
    expect(savedMessage({ skills_added: 0, fields: ["qualification"] })).toBe("Updated qualification.");
    expect(savedMessage({ skills_added: 0, fields: [] })).toBe("Nothing changed — the profile already had these values.");
  });
});
