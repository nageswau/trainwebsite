import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignCounselorButton from "@/components/AssignCounselorButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const USERS = [
  { id: "c1", name: "Asha Rao", division: "overseas", active: true },
  { id: "c2", name: "Old Hand", division: "overseas", active: false },
  { id: "c3", name: "IT Person", division: "it", active: true },
];

function stub(put: () => Promise<unknown>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? put() : json(200, USERS)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AssignCounselorButton", () => {
  it("lists active overseas counselors only and assigns one", async () => {
    const fetchMock = stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Choose…", "Asha Rao"]);
    fireEvent.change(select, { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Rao assigned.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/applications/a1/counselor", expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c1" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("reads Change counsellor when one is set, with no clear option", async () => {
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(select.value).toBe("c1");
    expect(Array.from(select.options).some((o) => o.value === "" && o.textContent !== "Choose…")).toBe(false);
  });

  it("shows the API's refusal", async () => {
    stub(() => json(409, { detail: "This application is closed" }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    fireEvent.change(await screen.findByLabelText("EduSphere counsellor"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This application is closed");
    expect(refresh).not.toHaveBeenCalled();
  });
});
