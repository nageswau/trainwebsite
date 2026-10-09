import { beforeEach, describe, expect, it, vi } from "vitest";

import MeetingActions from "@/components/MeetingActions";
import { serverApi } from "@/lib/api";
import MeetingPage from "@/app/partnership/meetings/[id]/page";
import { elements } from "@/tests/helpers/elementTree";
import { meeting } from "./meetingFixtures";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const ID = "3f2b6a8e-1c4d-4e5f-8a9b-0c1d2e3f4a5b";
const serve = (m: ReturnType<typeof meeting>) =>
  vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/auth/me" ? { role: "partnership_manager", full_name: "Rahul" } : { meeting: m }) as never);

beforeEach(() => vi.mocked(serverApi).mockReset());

describe("upc-009 meeting detail page", () => {
  it("QA-02: keeps the actions mounted after the outcome, so its confirmation survives the re-read", async () => {
    serve(meeting({ id: ID, status: "completed", completed_at: "2030-01-10T06:00:00Z", completed_by: { id: "p1", full_name: "Rahul", active: true } }));
    const tree = elements(await MeetingPage({ params: Promise.resolve({ id: ID }) }));
    expect(tree.find((el) => el.type === MeetingActions)).toBeDefined();
  });

  it("QA-03: the missing-link warning is styled as a warning", async () => {
    serve(meeting({ id: ID, mode: "online", warnings: ["link_missing"] }));
    const tree = elements(await MeetingPage({ params: Promise.resolve({ id: ID }) }));
    const note = tree.find((el) => el.props?.role === "note" && String(el.props?.children).includes("no link yet"));
    expect(note?.props.className).toBe("form-warning");
  });
});
