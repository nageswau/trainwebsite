import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolCoordinatorStudentDetailPage from "@/app/school/coordinator/students/[id]/page";
import { serverApi } from "@/lib/api";

// QA2-02 (ENH-025 exploratory QA): a Teacher who opened the coordinator's student URL got the coordinator shell, the
// transfer disclosure and the photo upload control -- controls that can only fail for them. The page now checks the
// role first, like /school/coordinator/transfers (ENH-005), and never loads the student for anyone else.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }));
vi.mock("@/components/SchoolStudentDetailPanel", () => ({
  default: ({ canEditPhoto, showTransfer }: { canEditPhoto?: boolean; showTransfer?: boolean }) => <div data-testid="panel">{`photo:${String(canEditPhoto)} transfer:${String(showTransfer)}`}</div>,
}));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "school", profile: {} });
const student = { id: "s1", student_code: "A3F9C21B", full_name: "Aarav Mehta", date_of_birth: null, grade_or_class: null, has_photo: false };

function serve(role: string) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role) as never;
    if (path === "/api/v1/school/students/s1") return student as never;
    throw new Error(`unexpected request ${path}`);
  });
}

const props = { params: Promise.resolve({ id: "s1" }) };

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolCoordinatorStudentDetailPage access", () => {
  it("shows the coordinator's student page, with photo and transfer controls, to a School Coordinator", async () => {
    serve("school_coordinator");
    render(await SchoolCoordinatorStudentDetailPage(props));
    expect(screen.getByTestId("panel").textContent).toBe("photo:true transfer:true");
  });

  it.each(["school_teacher", "school_principal", "school_parent", "career_counselor"])("denies %s with a clear message and never loads the student", async (role) => {
    serve(role);
    render(await SchoolCoordinatorStudentDetailPage(props));
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("School Coordinator role required")).toBeTruthy();
    expect(screen.queryByTestId("panel")).toBeNull();
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0])).not.toContain("/api/v1/school/students/s1");
  });
});
