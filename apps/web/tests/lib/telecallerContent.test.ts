import { describe, expect, it } from "vitest";

import { ASSET_KIND_LABEL, EMAIL_KINDS, KIND_LABEL, WHATSAPP_KINDS, formatBytes, kindsFor, unknownPlaceholders } from "@/lib/telecallerContent";

describe("tel-012 content library helpers", () => {
  it("labels the 9 WhatsApp (§11) and 7 email (§12) kinds in source order", () => {
    expect(WHATSAPP_KINDS).toHaveLength(9);
    expect(EMAIL_KINDS).toHaveLength(7);
    expect(kindsFor("whatsapp").map((k) => KIND_LABEL[k])).toEqual([
      "Welcome message", "Course details", "Brochure", "Fee details", "Counselling appointment", "Reminder", "Follow-up",
      "Overseas destination information", "Document request",
    ]);
    expect(kindsFor("email").map((k) => KIND_LABEL[k])).toEqual([
      "Course brochure", "Fee proposal", "Counselling confirmation", "Overseas information", "University information", "Follow-up",
      "Appointment confirmation",
    ]);
    expect(ASSET_KIND_LABEL).toEqual({ brochure: "Brochure", fee: "Fee sheet" });
  });

  it("finds unknown placeholders with the server's rule", () => {
    expect(unknownPlaceholders("Hi {name}, {product} at {appointment_time}: {brochure_link}")).toEqual([]);
    expect(unknownPlaceholders("Hi {Name} {discount} {name} { name }")).toEqual(["{Name}", "{discount}", "{ name }"]);
    expect(unknownPlaceholders("a lone { brace\n} and :}")).toEqual([]);
  });

  it("formats file sizes", () => {
    expect(formatBytes(900)).toBe("900 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3.5 * 1024 * 1024)).toBe("3.5 MB");
  });
});
