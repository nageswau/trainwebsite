import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PaymentModeBanner, { TEST_MODE_TEXT } from "@/components/PaymentModeBanner";

// nehn-022 (DEC-SCOPE-283) AC2: payment screens say plainly when Razorpay runs in test mode; live mode shows nothing.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function serve(response: () => Promise<Response>) {
  const fetchMock = vi.fn(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PaymentModeBanner (nehn-022)", () => {
  it("shows the test-mode banner in test mode", async () => {
    const fetchMock = serve(() => Promise.resolve(json({ mode: "test" })));
    render(<PaymentModeBanner />);
    expect(await screen.findByText(TEST_MODE_TEXT)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/payments/mode");
  });

  it("shows nothing in live mode", async () => {
    const fetchMock = serve(() => Promise.resolve(json({ mode: "live" })));
    const { container } = render(<PaymentModeBanner />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing while loading or when the read fails", async () => {
    serve(() => new Promise(() => {}));
    const pending = render(<PaymentModeBanner />);
    expect(pending.container).toBeEmptyDOMElement();
    cleanup();

    for (const failure of [() => Promise.resolve(json({ detail: "Not authenticated" }, 401)), () => Promise.reject(new Error("offline"))]) {
      const fetchMock = serve(failure);
      const { container } = render(<PaymentModeBanner />);
      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(container).toBeEmptyDOMElement();
      cleanup();
    }
  });
});
