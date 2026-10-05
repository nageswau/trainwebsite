import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerSignInPage from "@/app/telecaller/sign-in/page";

afterEach(cleanup);

async function renderWith(next?: string) {
  render(await TelecallerSignInPage({ searchParams: Promise.resolve(next === undefined ? {} : { next }) }));
}

describe("/telecaller/sign-in (tel-001 TL1)", () => {
  it("offers both team portals and Administration, carrying a same-site next (Administration only for manager pages)", async () => {
    await renderWith("/telecaller/dashboard");
    expect(screen.getByRole("heading", { level: 1, name: "Telecaller sign-in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login?next=%2Ftelecaller%2Fdashboard");
    expect(screen.getByRole("link", { name: "Overseas team" })).toHaveAttribute("href", "/overseas/login?next=%2Ftelecaller%2Fdashboard");
    expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute("href", "/admin/login");
  });

  it("keeps a manager next on the Administration link", async () => {
    await renderWith("/telecaller/manager/team");
    expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute("href", "/admin/login?next=%2Ftelecaller%2Fmanager%2Fteam");
  });

  it("drops an off-site next", async () => {
    await renderWith("https://evil.example/x");
    expect(screen.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login");
    expect(screen.getByRole("link", { name: "Overseas team" })).toHaveAttribute("href", "/overseas/login");
  });
});
