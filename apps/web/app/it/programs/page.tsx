import type { Metadata } from "next";

import ProgramCatalogue from "@/components/ProgramCatalogue";
import PublicShell from "@/components/PublicShell";
import { publicApi } from "@/lib/api";
import type { Program } from "@/lib/types";

import styles from "@/components/ProgramCatalogue.module.css";

export const metadata: Metadata = {
  title: "IT Training Programs",
  description: "Compare EduSphere IT training programs by skill area, duration, curriculum, fees, certification, and placement support.",
};

type ProgramsPageProps = {
  searchParams: Promise<{
    category?: string;
    q?: string;
    sort?: string;
    page?: string;
  }>;
};

export default async function ProgramsPage({ searchParams }: ProgramsPageProps) {
  const params = await searchParams;
  let programs: Program[] = [];
  let catalogueUnavailable = false;

  try {
    programs = await publicApi<Program[]>("/api/v1/public/programs");
  } catch {
    catalogueUnavailable = true;
  }

  const categories = new Set(programs.map((program) => program.category));
  const initialCategory = params.category && categories.has(params.category) ? params.category : "";
  const initialPage = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  return (
    <PublicShell division="it">
      <section className={styles.pageIntro}>
        <div className={`container ${styles.introGrid}`}>
          <div>
            <p className={styles.eyebrow}>IT Training Catalogue</p>
            <h1>Choose the skills you want to put to work.</h1>
            <p className={styles.introCopy}>
              Compare focused learning tracks, see exactly what each curriculum covers, and find the programme that fits your next career move.
            </p>
          </div>
          <aside className={styles.learningPromise} aria-label="What every programme includes">
            <span className={styles.promiseLabel}>Every Programme Includes</span>
            <strong>Instruction, practical work, and career support.</strong>
            <p>Open any programme to review its full curriculum, eligibility, certification, trainer, and placement assistance.</p>
          </aside>
        </div>
      </section>

      <section className={styles.catalogueSection} aria-labelledby="programme-catalogue-title">
        <div className="container">
          <div className={styles.catalogueHeading}>
            <div>
              <p className={styles.eyebrow}>Explore by Skill Area</p>
              <h2 id="programme-catalogue-title">Find your learning track</h2>
            </div>
            {!catalogueUnavailable && programs.length > 0 ? (
              <p className={styles.catalogueCount}>
                <strong>{programs.length}</strong> programmes across <strong>{categories.size}</strong> skill areas
              </p>
            ) : null}
          </div>

          <ProgramCatalogue
            programs={programs}
            unavailable={catalogueUnavailable}
            initialCategory={initialCategory}
            initialQuery={params.q ?? ""}
            initialSort={params.sort ?? "title-asc"}
            initialPage={initialPage}
          />
        </div>
      </section>
    </PublicShell>
  );
}
