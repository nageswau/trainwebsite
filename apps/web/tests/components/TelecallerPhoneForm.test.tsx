import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
});
