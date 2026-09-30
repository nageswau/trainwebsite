import { beforeEach, describe, expect, it, vi } from "vitest";

import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";
import ProfileForm from "@/components/ProfileForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import AccountProfilePage, { metadata } from "@/app/account/profile/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/components/PublicShell", () => ({ default: function PublicShell() { return null; } }));

const user = (overrides: Record<string, unknown> = {}) => ({ id: "u1", email: "coordinator@example.local", full_name: "Fatima Coordinator", role: "school_coordinator", division: "overseas", phone: "+91 90000 00000", profile: {}, ...overrides });

async function render() {
  return elements(await AccountProfilePage());
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("/account/profile page (ENH-007)", () => {
  it("shows the form for a signed-in School-domain user with their current name and phone", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const tree = await render();
    const form = tree.find((el) => el.type === ProfileForm)!;
    expect(form.props.fullName).toBe("Fatima Coordinator");
    expect(form.props.phone).toBe("+91 90000 00000");
    expect(tree.find((el) => el.type === PublicShell)!.props.division).toBe("overseas");
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Your profile");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("passes null, not undefined, when phone is unset", async () => {
    vi.mocked(serverApi).mockResolvedValue(user({ phone: undefined }));
    const tree = await render();
    expect(tree.find((el) => el.type === ProfileForm)!.props.phone).toBeNull();
  });

  it("links back to the role's own dashboard", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const back = (await render()).find((el) => el.props.href && text(el).includes("Back to dashboard"))!;
    expect(back.props.href).toBe("/school/coordinator/dashboard");
  });

  it("asks a signed-out visitor to sign in and returns them to this page afterwards", async () => {
    vi.mocked(serverApi).mockRejectedValue(new ApiError("Not authenticated", 401));
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Sign in required");
    const links = tree.filter((el) => el.type === "a").map((el) => el.props.href);
    expect(links).toEqual(["/it/login?next=%2Faccount%2Fprofile", "/overseas/login?next=%2Faccount%2Fprofile"]);
    expect(tree.some((el) => el.type === ProfileForm)).toBe(false);
  });

  it.each([
    ["the API answers 500", () => new ApiError("500 Internal Server Error", 500)],
    ["the API cannot be reached at all", () => new TypeError("fetch failed")],
  ])("says the service is unavailable, not \"sign in\", when %s", async (_label, failure) => {
    vi.mocked(serverApi).mockRejectedValue(failure());
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Temporarily unavailable");
    expect(tree.some((el) => el.type === ProfileForm)).toBe(false);
  });

  it("has a page title of its own", () => {
    expect(metadata.title).toBe("Your profile");
  });
});

const prefs = { whatsapp: true, sms: false, phone_valid: true };
function byPath(overrides: { me?: unknown; prefs?: unknown | Error } = {}) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/account/notification-preferences") {
      if (overrides.prefs instanceof Error) throw overrides.prefs;
      return overrides.prefs ?? prefs;
    }
    return overrides.me ?? user();
  });
}

describe("/account/profile notification section (ENH-014)", () => {
  it("renders the preferences form with the saved values and the user's phone", async () => {
    byPath();
    const tree = await render();
    const form = tree.find((el) => el.type === NotificationPreferencesForm)!;
    expect(form.props.initial).toEqual(prefs);
    expect(form.props.phone).toBe("+91 90000 00000");
    expect(text(tree.find((el) => el.type === "h2")!)).toBe("Notifications");
  });

  it("shows a section-only error when preferences fail to load, keeping the profile form", async () => {
    byPath({ prefs: new Error("boom") });
    const tree = await render();
    expect(tree.find((el) => el.type === ProfileForm)).toBeDefined();
    expect(tree.find((el) => el.type === NotificationPreferencesForm)).toBeUndefined();
    expect(tree.some((el) => text(el) === "We couldn't load your notification settings right now.")).toBe(true);
  });

  it("treats a malformed preferences body as a load failure", async () => {
    byPath({ prefs: { whatsapp: "yes" } });
    const tree = await render();
    expect(tree.find((el) => el.type === NotificationPreferencesForm)).toBeUndefined();
  });
});
