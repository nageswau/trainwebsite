import { describe, expect, it } from "vitest";

import { changedFields, displayValue, toForm, type FieldKey, type FieldValue } from "@/lib/candidatePortal";

const loaded = {
  name: "Asha", city: null, state: null, country: "India", linkedin: null, current_company: null, notice_days: 30, preferred_roles: ["Java dev"],
  tools: [], languages: ["English", "Hindi"], available_from: null, willing_to_relocate: true, preferred_contact: "email",
} as Record<FieldKey, FieldValue>;

describe("hrc-022 candidate portal form helpers", () => {
  it("shows every value as input text", () => {
    const form = toForm(loaded);
    expect(form.languages).toBe("English, Hindi");
    expect(form.willing_to_relocate).toBe("yes");
    expect(form.notice_days).toBe("30");
    expect(form.city).toBe("");
  });

  it("sends only changed, editable fields, parsed to their types", () => {
    const form = { ...toForm(loaded), city: " Pune ", notice_days: "45", tools: "Git, Docker", willing_to_relocate: "no", name: "Changed" };
    expect(changedFields(form, loaded, ["city", "notice_days", "tools", "willing_to_relocate"])).toEqual({
      city: "Pune", notice_days: 45, tools: ["Git", "Docker"], willing_to_relocate: false,
    });
  });

  it("clears a field with null and a list with []", () => {
    const form = { ...toForm(loaded), country: "", languages: "" };
    expect(changedFields(form, loaded, ["country", "languages"])).toEqual({ country: null, languages: [] });
  });

  it("sends nothing when nothing changed", () => {
    expect(changedFields(toForm(loaded), loaded, ["city", "country"])).toEqual({});
  });

  it("reads values for display", () => {
    expect(displayValue("city", null)).toBe("Not provided");
    expect(displayValue("tools", [])).toBe("Not provided");
    expect(displayValue("preferred_contact", "whatsapp")).toBe("WhatsApp");
    expect(displayValue("willing_to_relocate", false)).toBe("No");
  });
});
