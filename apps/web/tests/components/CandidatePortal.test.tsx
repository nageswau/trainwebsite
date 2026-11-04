import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CandidateProfileForm from "@/components/CandidateProfileForm";
import CandidateRegisterForm from "@/components/CandidateRegisterForm";
import CandidateVerifyEmail from "@/components/CandidateVerifyEmail";
import RecruiterSelfServiceSetting from "@/components/RecruiterSelfServiceSetting";
import type { CandidateProfile } from "@/lib/candidatePortal";

// hrc-022 (DEC-SCOPE-385): registration (C2), the click-to-verify link (C3), the own profile with only the allow-listed inputs (C11)
// and the managers' allow-list card (C7).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PROFILE: CandidateProfile = {
  candidate_code: "CAN-00042", name: "Asha K", email: "asha@example.com", email_verified: true, mobile: "+91 99887 76655", pending_email: null,
  fields: { name: "Asha K", city: null, state: null, country: "India", linkedin: null, current_company: null, notice_days: 30, preferred_roles: [],
            tools: [], languages: [], available_from: null, willing_to_relocate: null, preferred_contact: "email" },
  editable: ["city", "notice_days"],
};

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("CandidateRegisterForm", () => {
  it("refuses mismatched passwords without calling the server", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<CandidateRegisterForm />);
    fill(/Full name/, "Asha K");
    fill(/^Email/, "asha@example.com");
    fill(/^Password/, "Candidate@12345");
    fill(/Confirm password/, "Different@12345");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.submit(screen.getByRole("button", { name: "Create candidate account" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("The passwords do not match.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says only 'check your inbox' after registering, with the consent version", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ accepted: true }, 202)));
    vi.stubGlobal("fetch", fetchMock);
    render(<CandidateRegisterForm />);
    fill(/Full name/, "Asha K");
    fill(/^Email/, "asha@example.com");
    fill(/^Password/, "Candidate@12345");
    fill(/Confirm password/, "Candidate@12345");
    fireEvent.submit(screen.getByRole("button", { name: "Create candidate account" }).closest("form")!);
    expect(await screen.findByRole("status")).toHaveTextContent("Check your inbox at asha@example.com");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/candidate/register");
    expect(JSON.parse(String(init.body))).toMatchObject({ email: "asha@example.com", consent_version: "candidate-v1", phone: null });
  });
});

describe("CandidateVerifyEmail", () => {
  it("verifies only on a click", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ ok: true, purpose: "verify_email" })));
    vi.stubGlobal("fetch", fetchMock);
    render(<CandidateVerifyEmail token="abc" />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Verify my email" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your email is verified");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/it/login");
  });

  it("explains a dead link and offers a new one", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This link is invalid or has expired" }, 400))));
    render(<CandidateVerifyEmail token="dead" />);
    fireEvent.click(screen.getByRole("button", { name: "Verify my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is invalid or has expired");
    expect(screen.getByLabelText(/Your email, for a new link/)).toBeInTheDocument();
  });
});

describe("CandidateProfileForm", () => {
  it("offers inputs only for the allow-listed fields and sends only what changed", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ ...PROFILE, fields: { ...PROFILE.fields, city: "Pune" } })));
    vi.stubGlobal("fetch", fetchMock);
    render(<CandidateProfileForm initial={PROFILE} />);
    expect(screen.getByLabelText("City")).toBeInTheDocument();
    expect(screen.queryByLabelText("Country")).toBeNull();
    expect(screen.getByText("Kept by your recruiter")).toBeInTheDocument();
    fill(/^City/, "Pune");
    fireEvent.click(screen.getByRole("button", { name: "Save my details" }));
    expect(await screen.findByText("Your profile is saved.")).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ city: "Pune" });
  });

  it("shows the server's refusal", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "City cannot be changed here -- ask your recruiter" }, 403))));
    render(<CandidateProfileForm initial={PROFILE} />);
    fill(/^City/, "Pune");
    fireEvent.click(screen.getByRole("button", { name: "Save my details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("City cannot be changed here");
  });
});

describe("RecruiterSelfServiceSetting", () => {
  it("renders nothing for who may not change it", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ fields: ["city"], available: ["name", "city"], can_edit: false })));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<RecruiterSelfServiceSetting />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("saves the chosen fields", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(res(init?.method === "PUT" ? { fields: ["city", "name"], available: ["name", "city"], can_edit: true } : { fields: ["city"], available: ["name", "city"], can_edit: true })));
    vi.stubGlobal("fetch", fetchMock);
    render(<RecruiterSelfServiceSetting />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Full name" }));
    fireEvent.click(screen.getByRole("button", { name: "Save fields" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Candidates can now edit the chosen fields");
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ fields: ["city", "name"] });
  });
});
