import { Suspense, type ReactNode } from "react";

export default function ITLoginLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
