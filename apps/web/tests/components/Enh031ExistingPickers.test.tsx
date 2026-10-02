import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationCreatePanel from "@/components/AgentApplicationCreatePanel";
import SchoolPsychometricRecordsPanel from "@/components/SchoolPsychometricRecordsPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("existing student dropdowns are searchable (ENH-031 §3.2)", () => {
  it("the psychometric assign form filters its roster by typing", () => {
    const students = [
      { id: "s1", full_name: "Asha Rao", school_name: "Hill School" },
      { id: "s2", full_name: "Ravi Iyer", school_name: "Hill School" },
    ];
    render(<SchoolPsychometricRecordsPanel records={[]} students={students} />);
    const input = screen.getByRole("combobox", { name: "Student" });
    expect(input.id).toBe("psych-student");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ravi" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Ravi Iyer — Hill School"]);
  });

  it("the agent's Create application picker empties after a successful create", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/workflows/overseas/agent/crm/students")) return Promise.resolve(json({ items: [{ id: "s1", has_login: true, full_name: "Asha Rao", email: "asha@example.local", status: "active" }], total: 1, limit: 20, offset: 0 }));
      if (url === "/api/v1/public/universities") return Promise.resolve(json([{ id: "u1", slug: "u1", name: "Uni One", city: "X" }]));
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "POST") return Promise.resolve(json({ id: "app1" }, 201));
      return Promise.resolve(json({}));
    }));
    render(<AgentApplicationCreatePanel />);
    const input = await screen.findByRole("combobox", { name: "Linked student" });
    fireEvent.focus(input);
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — asha@example.local" }));
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: /Create application/ }));
    await screen.findByText("Application created.");
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Linked student" }) as HTMLInputElement).value).toBe(""));
  });
});
