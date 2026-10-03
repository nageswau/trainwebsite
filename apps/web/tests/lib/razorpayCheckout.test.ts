import { afterEach, describe, expect, it, vi } from "vitest";

import { openRazorpayCheckout } from "@/lib/razorpayCheckout";

// AGN-011: the Checkout.js steps shared by fee payments and agent deposits. Razorpay itself is stubbed; nothing leaves the test.
const order = { key_id: "rzp_test_x", provider_order_id: "order_1", amount: 50000.5, currency: "INR" };

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("openRazorpayCheckout", () => {
  it("opens Checkout with the order in paise and wires the callbacks", async () => {
    const opened = vi.fn();
    let options: Record<string, unknown> = {};
    vi.stubGlobal(
      "Razorpay",
      class {
        constructor(o: Record<string, unknown>) {
          options = o;
        }
        open = opened;
      },
    );
    const onPaid = vi.fn();
    const onDismiss = vi.fn();
    expect(await openRazorpayCheckout(order, { description: "University deposit", onPaid, onDismiss })).toBe(true);
    expect(opened).toHaveBeenCalledOnce();
    expect(options).toMatchObject({ key: "rzp_test_x", order_id: "order_1", amount: 5000050, currency: "INR", name: "EduSphere", description: "University deposit" });
    (options.handler as (r: unknown) => void)({ razorpay_payment_id: "p", razorpay_order_id: "order_1", razorpay_signature: "s" });
    (options.modal as { ondismiss: () => void }).ondismiss();
    expect(onPaid).toHaveBeenCalledWith({ razorpay_payment_id: "p", razorpay_order_id: "order_1", razorpay_signature: "s" });
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("answers false when the Checkout script cannot load", async () => {
    const pending = openRazorpayCheckout(order, { description: "x", onPaid: vi.fn(), onDismiss: vi.fn() });
    const script = document.querySelector<HTMLScriptElement>('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
    expect(script).not.toBeNull();
    script!.onerror?.(new Event("error"));
    expect(await pending).toBe(false);
  });
});
