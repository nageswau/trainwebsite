"use client";

import { useEffect, useState } from "react";

export const TEST_MODE_TEXT = "Test mode: payments here use Razorpay test mode and no real money is charged.";

// nehn-022 (DEC-SCOPE-282): the payment-screen banner. Shown only when the API reports test mode; nothing while loading, in live mode,
// or when the read fails (the API's startup check, not this banner, is what keeps test keys out of live). A plain <p>, no live region.
export default function PaymentModeBanner() {
  const [mode, setMode] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/payments/mode")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => active && setMode(data?.mode ?? null))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  return mode === "test" ? <p className="form-warning">{TEST_MODE_TEXT}</p> : null;
}
