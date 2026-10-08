// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, middleware } from "@/middleware";

function go(path: string, signedIn = false) {
  const req = new NextRequest(`http://localhost${path}`);
  if (signedIn) req.cookies.set("edusphere_access", "x");
  return middleware(req).headers.get("location");
}

describe("middleware /bdm (bdm-001 AC12)", () => {
  it("sends a signed-out manager route to the admin sign-in, keeping next", () => {
    expect(go("/bdm/manager/team?offset=50")).toBe("http://localhost/admin/login?next=%2Fbdm%2Fmanager%2Fteam%3Foffset%3D50");
    expect(go("/bdm/manager")).toBe("http://localhost/admin/login?next=%2Fbdm%2Fmanager");
  });

  it("sends other signed-out /bdm routes to the chooser", () => {
    expect(go("/bdm/my-day")).toBe("http://localhost/bdm/sign-in?next=%2Fbdm%2Fmy-day");
    expect(go("/bdm/managerial")).toBe("http://localhost/bdm/sign-in?next=%2Fbdm%2Fmanagerial");
  });

  it("leaves the chooser public, unrelated paths alone, and signed-in visits through", () => {
    expect(go("/bdm/sign-in")).toBeNull();
    expect(go("/bdmx")).toBeNull();
    expect(go("/bdm/my-day", true)).toBeNull();
  });

  it("keeps the existing portals unchanged and matches /bdm", () => {
    expect(go("/it/admin/users")).toBe("http://localhost/it/login?next=%2Fit%2Fadmin%2Fusers");
    expect(go("/overseas/agent/dashboard")).toBe("http://localhost/overseas/login?next=%2Foverseas%2Fagent%2Fdashboard");
    expect(go("/admin/bdms")).toBe("http://localhost/admin/login?next=%2Fadmin%2Fbdms");
    expect(go("/admin/login")).toBeNull();
    // QA-05: the admin portal's password-recovery pages are public, like /admin/login
    expect(go("/admin/forgot-password")).toBeNull();
    expect(go("/admin/reset-password?token=abc")).toBeNull();
    expect(go("/admin/forgot-passwordx")).toBe("http://localhost/admin/login?next=%2Fadmin%2Fforgot-passwordx");
    expect(config.matcher).toContain("/bdm/:path*");
  });
});

describe("middleware /partnership (upc-001 PU1)", () => {
  it("sends a signed-out head route to the admin sign-in, keeping next", () => {
    expect(go("/partnership/head/team?offset=50")).toBe("http://localhost/admin/login?next=%2Fpartnership%2Fhead%2Fteam%3Foffset%3D50");
    expect(go("/partnership/head")).toBe("http://localhost/admin/login?next=%2Fpartnership%2Fhead");
  });

  it("sends other signed-out /partnership routes to the overseas sign-in", () => {
    expect(go("/partnership/dashboard")).toBe("http://localhost/overseas/login?next=%2Fpartnership%2Fdashboard");
    expect(go("/partnership")).toBe("http://localhost/overseas/login?next=%2Fpartnership");
    expect(go("/partnership/headline")).toBe("http://localhost/overseas/login?next=%2Fpartnership%2Fheadline");
  });

  it("leaves signed-in users and look-alike paths alone", () => {
    expect(go("/partnershipx")).toBeNull();
    expect(go("/partnership/dashboard", true)).toBeNull();
    expect(go("/admin/partnership-managers")).toBe("http://localhost/admin/login?next=%2Fadmin%2Fpartnership-managers");
    expect(config.matcher).toContain("/partnership/:path*");
  });
});

describe("middleware /telecaller (tel-001 AC5, TL1)", () => {
  it("sends a signed-out manager route to the admin sign-in, keeping next", () => {
    expect(go("/telecaller/manager/team?offset=50")).toBe("http://localhost/admin/login?next=%2Ftelecaller%2Fmanager%2Fteam%3Foffset%3D50");
    expect(go("/telecaller/manager")).toBe("http://localhost/admin/login?next=%2Ftelecaller%2Fmanager");
  });

  it("sends other signed-out /telecaller routes to the chooser", () => {
    expect(go("/telecaller/dashboard")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller%2Fdashboard");
    expect(go("/telecaller")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller");
    expect(go("/telecaller/managerial")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller%2Fmanagerial");
  });

  it("leaves the chooser public, unrelated paths alone, and signed-in visits through", () => {
    expect(go("/telecaller/sign-in")).toBeNull();
    expect(go("/telecallerx")).toBeNull();
    expect(go("/telecaller/dashboard", true)).toBeNull();
    expect(go("/admin/telecallers")).toBe("http://localhost/admin/login?next=%2Fadmin%2Ftelecallers");
    expect(config.matcher).toContain("/telecaller/:path*");
    expect(go("/bdm/my-day")).toBe("http://localhost/bdm/sign-in?next=%2Fbdm%2Fmy-day");
  });
});

describe("middleware /recruiter (rec-001, Q-29)", () => {
  it("sends a signed-out manager route to the admin sign-in, keeping next", () => {
    expect(go("/recruiter/manager/team?offset=50")).toBe("http://localhost/admin/login?next=%2Frecruiter%2Fmanager%2Fteam%3Foffset%3D50");
    expect(go("/recruiter/manager")).toBe("http://localhost/admin/login?next=%2Frecruiter%2Fmanager");
  });

  it("sends other signed-out /recruiter routes to the IT sign-in", () => {
    expect(go("/recruiter/dashboard")).toBe("http://localhost/it/login?next=%2Frecruiter%2Fdashboard");
    expect(go("/recruiter")).toBe("http://localhost/it/login?next=%2Frecruiter");
    expect(go("/recruiter/managerial")).toBe("http://localhost/it/login?next=%2Frecruiter%2Fmanagerial");
  });

  it("leaves unrelated paths alone and lets signed-in visits through", () => {
    expect(go("/recruiterx")).toBeNull();
    expect(go("/recruiter/dashboard", true)).toBeNull();
    expect(go("/admin/recruiter-staff")).toBe("http://localhost/admin/login?next=%2Fadmin%2Frecruiter-staff");
    expect(config.matcher).toContain("/recruiter/:path*");
  });
});

describe("middleware /it/counselor (tel-017)", () => {
  it("protects the IT counselor workspace like the other IT portals", () => {
    expect(go("/it/counselor/leads")).toBe("http://localhost/it/login?next=%2Fit%2Fcounselor%2Fleads");
    expect(go("/it/counselor")).toBe("http://localhost/it/login?next=%2Fit%2Fcounselor");
    expect(go("/it/counselor/dashboard", true)).toBeNull();
    expect(go("/overseas/counselor/dashboard")).toBe("http://localhost/overseas/login?next=%2Foverseas%2Fcounselor%2Fdashboard");
  });
});
