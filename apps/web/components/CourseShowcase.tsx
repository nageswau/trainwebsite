import Link from "next/link";
import type { CSSProperties } from "react";

import { programVisual } from "@/lib/programVisuals";
import type { Program } from "@/lib/types";

import styles from "./CourseShowcase.module.css";

/** Up to `limit` courses for the home grid: ones with an uploaded image first, then one course per category in turn, so six cards are
 * six different courses rather than the first category's tiles. Order within each group follows the API (category, title). */
export function pickShowcase(programs: Program[], limit = 6): Program[] {
  const picked = programs.filter((p) => p.image_url).slice(0, limit);
  const queues = new Map<string, Program[]>();
  for (const p of programs) if (!p.image_url) queues.set(p.category, [...(queues.get(p.category) ?? []), p]);
  while (picked.length < limit && [...queues.values()].some((q) => q.length)) {
    for (const q of queues.values()) {
      const next = q.shift();
      if (next && picked.length < limit) picked.push(next);
    }
  }
  return picked;
}

// PUB-025 (DEC-SCOPE-334): the /it home's "Explore Our Courses" grid, modelled loosely on eduspherecourses.in's #courses-section
// (UX_REFERENCE): up to six varied cards of image, title, short description and "View Details →". A course without an uploaded image
// shows its generated category tile.
export default function CourseShowcase({ programs }: { programs: Program[] }) {
  if (programs.length === 0) return null;
  return (
    <section className={`section ${styles.section}`} id="courses-section" aria-labelledby="courses-section-title">
      <div className="container">
        <div className={styles.heading}>
          <div>
            <div className="eyebrow">IT Training</div>
            <h2 id="courses-section-title">Explore Our Courses</h2>
          </div>
          <Link className="btn secondary" href="/it/programs">View all courses</Link>
        </div>
        <ul className={styles.grid}>
          {pickShowcase(programs).map((program) => {
            const visual = programVisual(program.category);
            return (
              <li key={program.id} className={styles.card} style={{ "--course-accent": visual.accent } as CSSProperties}>
                <div className={styles.media}>
                  {program.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- served by the API, sized by CSS
                    <img src={program.image_url} alt="" loading="lazy" />
                  ) : (
                    <span className={styles.tile} aria-hidden="true">{visual.mark}</span>
                  )}
                </div>
                <div className={styles.body}>
                  <span className={styles.category}>{program.category}</span>
                  <h3>{program.title}</h3>
                  <p>{program.summary}</p>
                  <Link className={styles.link} href={`/it/programs/${program.slug}`}>
                    View Details <span aria-hidden="true">→</span>
                    <span className="visually-hidden"> about {program.title}</span>
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
