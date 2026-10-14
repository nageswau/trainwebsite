import { describe, expect, it } from "vitest";

import { changeText, firstName, greeting } from "@/lib/managementHome";

describe("mgmt-031 managementHome", () => {
  it("greets by the IST hour (HM3), whatever the server's zone", () => {
    expect(greeting(new Date("2026-10-14T00:00:00Z"))).toBe("Good morning"); // 05:30 IST
    expect(greeting(new Date("2026-10-14T06:29:00Z"))).toBe("Good morning"); // 11:59 IST
    expect(greeting(new Date("2026-10-14T06:30:00Z"))).toBe("Good afternoon"); // 12:00 IST
    expect(greeting(new Date("2026-10-14T11:30:00Z"))).toBe("Good evening"); // 17:00 IST
    expect(greeting(new Date("2026-10-14T19:00:00Z"))).toBe("Good morning"); // 00:30 IST the next day
  });

  it("uses the first name", () => {
    expect(firstName("  Arjun Kumar ")).toBe("Arjun");
    expect(firstName("Root")).toBe("Root");
  });

  it("writes a month-on-month change with its sign", () => {
    expect(changeText(12.5)).toBe("+12.5%");
    expect(changeText(-4)).toBe("−4%");
    expect(changeText(0)).toBe("0%");
  });
});
