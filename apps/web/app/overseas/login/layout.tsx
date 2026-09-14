import { Suspense, type ReactNode } from "react";

export default function OverseasLoginLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
