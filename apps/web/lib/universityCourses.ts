import { useEffect, useState } from "react";

export type Course = { id: string; title: string; level: string };

// AGN-008: a university's courses for the application create and edit forms. null with no university and until the first list
// arrives; [] when the lookup fails. A response for a university that is no longer selected is ignored. Switching universities
// keeps the previous list on screen until the new one arrives, as the forms did before this hook.
export function useUniversityCourses(slug: string | null): Course[] | null {
  const [courses, setCourses] = useState<Course[] | null>(null);

  useEffect(() => {
    if (!slug) return setCourses(null);
    let cancelled = false;
    fetch(`/api/v1/public/universities/${slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return slug ? courses : null;
}
