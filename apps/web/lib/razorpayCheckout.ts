// Razorpay Checkout.js steps shared by student fee payments (PAY-001/STU-010) and agent deposits (AGN-011): load the script on demand
// and open Checkout for an order the API created. The API is the authority on amount and order; the browser only shows Razorpay's
// window and hands its signed result back to `/payments/{id}/verify`.

export type RazorpaySuccessResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

type RazorpayCheckoutOptions = {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  handler: (response: RazorpaySuccessResponse) => void;
  modal?: { ondismiss?: () => void };
};

type RazorpayCheckoutInstance = { open: () => void };

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayCheckoutOptions) => RazorpayCheckoutInstance;
  }
}

// What a checkout endpoint returns once an order exists: the public key id only, never a secret.
export type RazorpayOrder = { key_id: string; provider_order_id: string; amount: number; currency: string };

const CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";

// Loaded on demand rather than only trusting a <Script> tag's own timing -- a slow network could still have a user click "Pay" before
// it finishes.
export function loadRazorpayCheckout(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (window.Razorpay) return Promise.resolve(true);
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SCRIPT;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

// Opens Checkout for `order`; false when the script could not load (nothing was opened, nothing charged).
export async function openRazorpayCheckout(
  order: RazorpayOrder,
  { description, onPaid, onDismiss }: { description: string; onPaid: (response: RazorpaySuccessResponse) => void; onDismiss: () => void },
): Promise<boolean> {
  const ready = await loadRazorpayCheckout();
  if (!ready || !window.Razorpay) return false;
  new window.Razorpay({
    key: order.key_id,
    order_id: order.provider_order_id,
    amount: Math.round(order.amount * 100),
    currency: order.currency,
    name: "EduSphere",
    description,
    handler: onPaid,
    modal: { ondismiss: onDismiss },
  }).open();
  return true;
}
