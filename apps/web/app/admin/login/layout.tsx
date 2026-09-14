import { Suspense, type ReactNode } from "react";

export default function AdminLoginLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
