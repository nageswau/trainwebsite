import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterForm from "@/components/RegisterForm";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Rao" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.local" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Sup3r-Secret-Pass!" } });
}

function pdf(name = "doc.pdf", size = 20) {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

function fillKyc(overrides: Partial<Record<"pan" | "aadhaar" | "license", File>> = {}) {
  fireEvent.change(screen.getByLabelText("PAN number"), { target: { value: "abcde1234f" } });
  fireEvent.change(screen.getByLabelText("Aadhaar (last 4 digits)"), { target: { value: "1234" } });
  fireEvent.change(screen.getByLabelText("Business licence number"), { target: { value: "LIC-2026/001" } });
  fireEvent.change(screen.getByLabelText(/^PAN card/), { target: { files: [overrides.pan ?? pdf("pan.pdf")] } });
  fireEvent.change(screen.getByLabelText(/^Aadhaar card/), { target: { files: [overrides.aadhaar ?? pdf("aadhaar.pdf")] } });
  fireEvent.change(screen.getByLabelText(/^Business licence \(/), { target: { files: [overrides.license ?? pdf("licence.pdf")] } });
}

// jsdom runs constraint validation on a submit-button click and its file inputs never hold the files fireEvent sets, so the
// agent tests submit the form directly; the client-side checks in `submit` are what they exercise.
function submitForm() {
  fireEvent.submit(screen.getByRole("button", { name: "Create account" }).closest("form") as HTMLFormElement);
}

describe("RegisterForm (AGN-001)", () => {
  it("shows the agency name field only for an education agent", () => {
    render(<RegisterForm division="overseas" />);
    expect(screen.queryByLabelText("Agency name (optional)")).toBeNull();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    expect(screen.getByLabelText("Agency name (optional)")).toHaveAttribute("maxLength", "160");
  });

  it("sends no agency_name for a student", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "overseas_student" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(mock.mock.calls[0][1].body)).not.toHaveProperty("agency_name");
  });
});

describe("RegisterForm KYC (AGN-024)", () => {
  it("shows the verification documents only for an education agent (AGN-024)", () => {
    render(<RegisterForm division="overseas" />);
    expect(screen.queryByLabelText("PAN number")).toBeNull();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    expect(screen.getByLabelText(/^PAN card/)).toHaveAttribute("accept", ".pdf,.jpg,.jpeg,.png");
    expect(screen.getByLabelText(/^PAN card/)).toBeRequired();
    expect(screen.getByText("Only the last 4 digits are stored.")).toBeInTheDocument();
  });

  it("sends an agent signup as multipart with the three files and numbers, then opens the status page", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "agent" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agency name (optional)"), { target: { value: "ABC Overseas" } });
    fillKyc();
    submitForm();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/agent/registration-status"));
    const init = mock.mock.calls[0][1] as RequestInit;
    expect(init.headers).toBeUndefined();
    const body = init.body as FormData;
    expect(body.get("account_type")).toBe("agent");
    expect(body.get("agency_name")).toBe("ABC Overseas");
    expect(body.get("pan_number")).toBe("ABCDE1234F");
    expect(body.get("aadhaar_last4")).toBe("1234");
    expect((body.get("license_file") as File).name).toBe("licence.pdf");
  });

  it("blocks an oversize or wrong-type file before sending, naming the document", async () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    fillKyc({ aadhaar: pdf("aadhaar.pdf", 5 * 1024 * 1024 + 1) });
    submitForm();
    expect(await screen.findByRole("alert")).toHaveTextContent("Aadhaar card: the file must be at most 5 MB.");
    fillKyc({ license: new File(["x"], "licence.exe", { type: "application/octet-stream" }) });
    submitForm();
    expect(await screen.findByRole("alert")).toHaveTextContent("Business licence: upload a PDF, JPG or PNG file.");
    expect(mock).not.toHaveBeenCalled();
  });
});
