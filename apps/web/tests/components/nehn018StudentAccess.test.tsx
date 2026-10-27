import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminStudentAccessPanel from "@/components/AdminStudentAccessPanel";
import LiveClassesPanel from "@/components/LiveClassesPanel";
import LockedFeatureCard from "@/components/LockedFeatureCard";
import PortalPage from "@/components/PortalPage";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";
import { featureLock, withLocks, type StudentAccess } from "@/lib/studentAccess";

// nehn-018 (DEC-SCOPE-303): a locked student feature shows "Complete payment to unlock" (AC1), the sidebar marks it, and the IT admin
// edits the policy (AC4).
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({
  notFound: () => { throw new Error("notFound"); },
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/it/student/attendance",
  useSearchParams: () => new URLSearchParams(""),
}));
vi.mock("@/components/WorkflowPanel", () => ({ default: ({ liveClassesLock }: { liveClassesLock?: unknown }) => <p>{liveClassesLock ? "workflow panel (live classes locked)" : "workflow panel"}</p> }));

const api = vi.mocked(serverApi);
const student = { id: "s1", role: "it_student", division: "it", full_name: "Arjun", email: "a@example.local", profile: {} };
const LOCK = { feature: "attendance", label: "Attendance", required_state: "partially_paid", current_state: "enrolled_pending_payment" } as const;
const section = (extra: Record<string, unknown> = {}) => ({ title: "Attendance & Progress", subtitle: "Session records.", metrics: [], actions: [], columns: [], rows: [], panels: [], ...extra });
const access = (locked: string[]): StudentAccess => ({
  state: "enrolled_pending_payment",
  features: ["attendance", "assignments", "questions"].map((key) => ({ key, label: key, unlocked: !locked.includes(key), required_state: "partially_paid" })),
});

function answer(payload: Record<string, unknown>, summary: StudentAccess) {
  api.mockImplementation((path: string) =>
    Promise.resolve(path === "/api/v1/auth/me" ? student : path === "/api/v1/workflows/it/student/access" ? summary : payload),
  );
}

beforeEach(() => api.mockReset());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LockedFeatureCard", () => {
  it("says what is locked, why, and links to the fees page", () => {
    render(<LockedFeatureCard lock={LOCK} />);
    expect(screen.getByRole("heading", { name: "Attendance is locked" })).toBeInTheDocument();
    expect(screen.getByText(/opens once your first payment is made/)).toBeInTheDocument();
    expect(screen.getByText("Your payment status: Enrolled, payment pending")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Complete payment to unlock" })).toHaveAttribute("href", "/it/student/fees");
  });

  it("asks a student with no enrolment to choose a course instead", () => {
    render(<LockedFeatureCard lock={{ ...LOCK, current_state: "registered" }} />);
    expect(screen.getByRole("link", { name: "Choose a course" })).toHaveAttribute("href", "/it/student/course");
    expect(screen.queryByRole("link", { name: "Complete payment to unlock" })).toBeNull();
  });
});

describe("PortalPage for a locked student section", () => {
  it("shows the heading and the locked card instead of the table and actions, and badges the locked nav items", async () => {
    answer(section({ locked: LOCK }), access(["attendance", "questions"]));
    const { container } = render(await PortalPage({ division: "it", role: "student", section: "attendance" }));
    expect(screen.getByRole("heading", { level: 2, name: "Attendance & Progress" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Attendance is locked" })).toBeInTheDocument();
    expect(screen.queryByText("No records yet")).toBeNull();
    expect(screen.queryByText("workflow panel")).toBeNull();
    const nav = container.querySelector(".portal-nav") as HTMLElement;
    expect(within(nav).getByRole("link", { name: "Attendance Locked" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Questions Locked" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Assignments" })).toBeInTheDocument();
  });

  it("renders an open section as before", async () => {
    answer(section(), access([]));
    render(await PortalPage({ division: "it", role: "student", section: "attendance" }));
    expect(screen.queryByRole("heading", { name: "Attendance is locked" })).toBeNull();
    expect(screen.getByText("workflow panel")).toBeInTheDocument();
  });

  it("hands the Course page's live-classes lock to the action panels (QA18-02)", async () => {
    answer(section({ title: "Course Enrolled" }), { ...access([]), features: [{ key: "live_classes", label: "Live classes", unlocked: false, required_state: "partially_paid" }] });
    render(await PortalPage({ division: "it", role: "student", section: "course" }));
    expect(screen.getByText("workflow panel (live classes locked)")).toBeInTheDocument();
  });

  it("keeps the page when the access summary cannot be read (no badges)", async () => {
    api.mockImplementation((path: string) =>
      path === "/api/v1/workflows/it/student/access" ? Promise.reject(new Error("down")) : Promise.resolve(path === "/api/v1/auth/me" ? student : section()),
    );
    const { container } = render(await PortalPage({ division: "it", role: "student", section: "attendance" }));
    expect(screen.getByRole("heading", { level: 2, name: "Attendance & Progress" })).toBeInTheDocument();
    expect(container.querySelector(".nav-locked")).toBeNull();
  });
});

describe("withLocks", () => {
  it("marks every page of a locked feature (assignments covers projects)", () => {
    const nav: NavItem[] = [{ label: "Assignments", href: "/it/student/assignments" }, { label: "Projects", href: "/it/student/projects" }, { label: "Fees", href: "/it/student/fees" }];
    expect(withLocks(nav, access(["assignments"])).map((x) => Boolean(x.locked))).toEqual([true, true, false]);
    expect(withLocks(nav, null)).toBe(nav);
  });

  it("says Locked in words in the mobile menu", () => {
    render(<PortalShell nav={[{ label: "Attendance", href: "/it/student/attendance", locked: true }]} roleLabel="IT Student" userName="Arjun"><p>page</p></PortalShell>);
    expect(screen.getAllByRole("link", { name: "Attendance (locked)", hidden: true }).length).toBe(1);
  });
});

describe("LiveClassesPanel", () => {
  it("shows the locked card when live classes need payment", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({ detail: { ...LOCK, feature: "live_classes", label: "Live classes", code: "payment_required", message: "Complete your payment to unlock Live classes." } }) }));
    render(<LiveClassesPanel />);
    expect(await screen.findByRole("heading", { name: "Live classes is locked" })).toBeInTheDocument();
  });

  it("does not ask for sessions it already knows are locked (QA18-02: no 403 in the console)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveClassesPanel lock={{ ...LOCK, feature: "live_classes", label: "Live classes" }} />);
    expect(screen.getByRole("heading", { name: "Live classes is locked" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("featureLock", () => {
  it("builds a feature's lock from the access summary, or null when open or unknown", () => {
    const summary = { state: "enrolled_pending_payment", features: [{ key: "live_classes", label: "Live classes", unlocked: false, required_state: "partially_paid" }] } as StudentAccess;
    expect(featureLock(summary, "live_classes")).toEqual({ feature: "live_classes", label: "Live classes", required_state: "partially_paid", current_state: "enrolled_pending_payment" });
    expect(featureLock({ ...summary, features: [{ ...summary.features[0], unlocked: true }] }, "live_classes")).toBeNull();
    expect(featureLock(null, "live_classes")).toBeNull();
  });
});

describe("AdminStudentAccessPanel", () => {
  const rules = {
    rules: [{ feature: "attendance", label: "Attendance", min_state: "partially_paid" }, { feature: "questions", label: "Questions", min_state: "partially_paid" }],
    states: [{ key: "registered", label: "Registered" }, { key: "enrolled_pending_payment", label: "Enrolled, payment pending" }, { key: "partially_paid", label: "First payment made" }, { key: "fully_paid", label: "Fully paid" }],
  };

  it("loads the policy and saves every feature's state", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(rules) }).mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(rules) });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminStudentAccessPanel />);
    fireEvent.change(await screen.findByLabelText("Attendance"), { target: { value: "fully_paid" } });
    fireEvent.click(screen.getByRole("button", { name: "Save access rules" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/workflows/it/student-access/rules");
    expect(JSON.parse(init.body)).toEqual({ rules: { attendance: "fully_paid", questions: "partially_paid" } });
    expect(await screen.findByRole("status")).toHaveTextContent("Access rules saved");
  });

  it("shows the server's refusal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({ detail: "You do not have permission to change student access rules" }) }));
    render(<AdminStudentAccessPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to change student access rules");
  });
});
