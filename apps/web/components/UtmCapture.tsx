"use client";

import { useEffect } from "react";

import { captureUtm } from "@/lib/utm";

// hrc-023 (DEC-SCOPE-389 W1): keeps the landing page's campaign parameters for the visit. Renders nothing.
export default function UtmCapture() {
  useEffect(() => captureUtm(), []);
  return null;
}
