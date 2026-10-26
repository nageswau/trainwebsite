import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminAuditLog from "@/components/AdminAuditLog";
import AdminAuditLogPage from "@/components/AdminAuditLogPage";
import WorkflowPanel from "@/components/WorkflowPanel";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const it_admin = { id: "u", role: "it_admin", full_name: "Ira", division: "it", email: "i@x", profile: {} };
const props = { base: "/it/admin/audit-log", role: "it_admin" as const, nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator", loginHref: "/it/login" };
const signedInAs = (user: unknown, rows: unknown = []) => vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? user : rows) as never);
const auditCalls = () => vi.mocked(serverApi).mock.calls.map(([path]) => path).filter((path) => path !== "/api/v1/auth/me");

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("AdminAuditLogPage (nehn-042)", () => {
  it("reads one page (plus one row) with the address's filters; a division admin gets no Division filter and no Export", async () => {
    signedInAs(it_admin, [{ id: "r1" }]);
    const tree = elements(await AdminAuditLogPage({ ...props, searchParams: { entity_type: "payment", entity_id: "P-1" } }));
    expect(auditCalls()).toEqual(["/api/v1/admin/audit?entity_type=payment&entity_id=P-1&limit=51"]);
    const log = tree.find((el) => el.type === AdminAuditLog)!;
    expect(log.props.rows).toEqual([{ id: "r1" }]);
    expect(log.props.showDivision).toBe(false);
    expect(tree.some((el) => el.type === WorkflowPanel)).toBe(false);
  });

  it("gives the Super Admin the Division filter and keeps the Export panel", async () => {
    signedInAs({ ...it_admin, role: "super_admin", division: "global" });
    const tree = elements(await AdminAuditLogPage({ ...props, base: "/admin/security-logs", role: "super_admin", nav: SUPER_ADMIN_NAV, roleLabel: "Super Administrator", searchParams: {} }));
    expect(tree.find((el) => el.type === AdminAuditLog)!.props.showDivision).toBe(true);
    expect(tree.find((el) => el.type === WorkflowPanel)!.props.section).toBe("security-logs");
  });

  it("refuses any other role before reading the log", async () => {
    signedInAs({ ...it_admin, role: "overseas_admin", division: "overseas" });
    const tree = elements(await AdminAuditLogPage({ ...props, searchParams: {} }));
    expect(auditCalls()).toEqual([]);
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("IT Administrator role required");
  });

  it("explains a mistyped actor without asking the API", async () => {
    signedInAs(it_admin);
    const tree = elements(await AdminAuditLogPage({ ...props, searchParams: { actor: "Asha" } }));
    expect(auditCalls()).toEqual([]);
    const log = tree.find((el) => el.type === AdminAuditLog)!;
    expect(log.props.rows).toBeNull();
    expect(log.props.error).toMatch(/user reference/);
  });

  it("shows the API's worded 422, a generic line for an unworded one, and an unavailable line otherwise", async () => {
    for (const [failure, expected] of [
      [new ApiError("The end date must be on or after the start date", 422), "The end date must be on or after the start date"],
      [new ApiError("[object Object]", 422), "These filters could not be applied. Check them and try again."],
      [new ApiError("Internal Server Error", 500), "The audit log is unavailable right now. Please try again."],
    ] as const) {
      vi.mocked(serverApi).mockReset();
      vi.mocked(serverApi).mockImplementation(async (path: string) => {
        if (path === "/api/v1/auth/me") return it_admin as never;
        throw failure;
      });
      const tree = elements(await AdminAuditLogPage({ ...props, searchParams: {} }));
      expect(tree.find((el) => el.type === AdminAuditLog)!.props.error).toBe(expected);
    }
  });
});
