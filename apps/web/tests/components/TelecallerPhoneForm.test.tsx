import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("TelecallerPhoneForm (tel-001 TL3)", () => {
  it("PATCHes only the phone, announces success and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: "+91 98" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone="+91 11" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "+91 98" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    expect(await screen.findByText("Mobile saved.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/telecaller/profile");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ phone: "+91 98" });
    expect(refresh).toHaveBeenCalled();
  });

  it("PATCHes the given url instead (upc-001 PU3: the partnership manager's profile)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: "+91 98" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone={null} url="/api/v1/partnership/profile" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "+91 98" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    expect(await screen.findByText("Mobile saved.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/profile");
  });

  it("sends null for an empty field (clears it)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: null }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone="+91 11" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ phone: null });
  });

  it("shows the server's message, keeps the typed value and focuses the message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Phone may contain only digits, spaces and + - ( )" }, 422)));
    render(<TelecallerPhoneForm phone={null} />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    const message = await screen.findByText("Phone may contain only digits, spaces and + - ( )");
    expect(screen.getByLabelText("Mobile")).toHaveValue("abc");
    await waitFor(() => expect(document.activeElement).toBe(message));
    expect(refresh).not.toHaveBeenCalled();
  });

  // tel-001 QA-05: a second click while the first save is in flight sends nothing.
  it("sends one PATCH for two clicks in the same instant", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: "+91 98" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone={null} />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "+91 98" } });
    const button = screen.getByRole("button", { name: "Save mobile" });
    // One act() = no re-render between the clicks, exactly like two clicks in the same instant.
    act(() => {
      button.click();
      button.click();
    });
    expect(await screen.findByText("Mobile saved.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // tel-001 QA-06: after a save the field shows what was stored (trimmed, or empty when cleared), not the raw typing.
  it("shows the stored value after saving", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ phone: "+91 98" })));
    render(<TelecallerPhoneForm phone={null} />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "  +91 98  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    await screen.findByText("Mobile saved.");
    expect(screen.getByLabelText("Mobile")).toHaveValue("+91 98");
  });

  it("shows an empty field after clearing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ phone: null })));
    render(<TelecallerPhoneForm phone="+91 11" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    await screen.findByText("Mobile saved.");
    expect(screen.getByLabelText("Mobile")).toHaveValue("");
  });
});
