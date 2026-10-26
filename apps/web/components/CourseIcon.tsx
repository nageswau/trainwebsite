import type { ReactNode } from "react";

import { courseIconKey, type CourseIconKey } from "@/lib/courseIcons";

// nehn-036 (DEC-SCOPE-284 I2, I7): a decorative subject icon before a course (the title/category is always beside it, so aria-hidden).
// Drawn from this fixed set only -- never markup from the API -- and server-safe so public pages stay server-rendered.
const SHAPES: Record<CourseIconKey, ReactNode> = {
  ai: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M10 10h4v4h-4zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></>,
  security: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></>,
  data: <path d="M3 3v18h18M8 17v-5M13 17V8M18 17v-9" />,
  computing: <path d="m16 18 6-6-6-6M8 6l-6 6 6 6" />,
  engineering: <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" />,
  business: <><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2M2 13h20" /></>,
  health: <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />,
  hospitality: <path d="M3 18h18M5 18a7 7 0 0 1 14 0M12 11V8M10 8h4" />,
  law: <path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" />,
  education: <path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z" />,
  arts: <><path d="M12 2a10 10 0 0 0 0 20c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A5.6 5.6 0 0 0 22 9.8C22 5.5 17.5 2 12 2z" /><circle cx="7.5" cy="10.5" r="1" /><circle cx="12" cy="7" r="1" /><circle cx="16.5" cy="10.5" r="1" /></>,
  science: <path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7 15h10" />,
  general: <path d="M22 10 12 5 2 10l10 5 10-5zM6 12v5c3 2 9 2 12 0v-5M22 10v6" />,
};
const SIZES = { inline: 20, card: 36 } as const;

export default function CourseIcon({ icon, category, size = "inline" }: { icon?: string | null; category: string; size?: keyof typeof SIZES }) {
  const key = courseIconKey(icon, category);
  return (
    <svg className={`course-icon course-icon--${size}`} data-icon={key} width={SIZES[size]} height={SIZES[size]} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {SHAPES[key]}
    </svg>
  );
}
