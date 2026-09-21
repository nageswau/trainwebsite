import { beforeEach, describe, expect, it, vi } from "vitest";

import { serverApi } from "@/lib/api";
import EmployerDashboardPage from "@/app/it/employer/dashboard/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const profile = { full_name: "Asha Rao", email: "asha@example.local", phone: null, company_name: "Acme Ltd", company_website: null, registration_status: null };

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

// ENH-006 QA-003: the Employer dashboard is a standalone page (no PortalShell, no site header), so neither of the
// entry points other roles get reaches it; without its own link an employer would have to type the URL.
describe("Employer dashboard (ENH-006 entry point)", () => {
  it("links a signed-in employer to the change-password page", async () => {
    vi.mocked(serverApi).mockResolvedValue(profile);
    const link = elements(await EmployerDashboardPage()).find((el) => el.props.href === "/account/password")!;
    expect(link).toBeDefined();
    expect(text(link)).toBe("Change password");
  });

  it("keeps its existing sign-in card, with no change-password link, for a visitor without an employer session", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    const tree = elements(await EmployerDashboardPage());
    expect(tree.some((el) => el.type === "h1" && text(el) === "Sign in required")).toBe(true);
    expect(tree.some((el) => el.props.href === "/account/password")).toBe(false);
  });
});
