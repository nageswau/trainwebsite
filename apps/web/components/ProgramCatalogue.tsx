"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useMemo, useState } from "react";

import type { Program } from "@/lib/types";

import styles from "./ProgramCatalogue.module.css";

const PAGE_SIZE = 9;

const feeFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const categoryVisuals: Record<string, { accent: string; mark: string }> = {
  "Software Development": { accent: "#0878d1", mark: "</>" },
  Data: { accent: "#6d4bd3", mark: "01" },
  SAP: { accent: "#007f72", mark: "SAP" },
  Cloud: { accent: "#15865e", mark: "CLD" },
  "Artificial Intelligence": { accent: "#8450cc", mark: "AI" },
  "Cyber Security": { accent: "#d05b3f", mark: "SEC" },
  DevOps: { accent: "#26708e", mark: "OPS" },
};

type SortOption = "title-asc" | "fee-asc" | "fee-desc" | "duration-asc";

type CatalogueState = {
  category: string;
  query: string;
  sort: SortOption;
  page: number;
};

function durationInWeeks(duration: string) {
  const value = Number.parseFloat(duration);
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

function updateCatalogueUrl(state: CatalogueState) {
  const params = new URLSearchParams(window.location.search);
  const updates: Array<[string, string | number, string | number]> = [
    ["category", state.category, ""],
    ["q", state.query.trim(), ""],
    ["sort", state.sort, "title-asc"],
    ["page", state.page, 1],
  ];

  for (const [key, value, defaultValue] of updates) {
    if (value === defaultValue || value === "") params.delete(key);
    else params.set(key, String(value));
  }

  const query = params.toString();
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function FactIcon({ kind }: { kind: "duration" | "certificate" | "placement" }) {
  if (kind === "duration") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" />
        <path d="M12 7v5l3 2" />
      </svg>
    );
  }
  if (kind === "certificate") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 4h10v11H7z" />
        <path d="m9 15-1 5 4-2 4 2-1-5" />
        <path d="M10 8h4M10 11h4" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 18h16M6 18v-5h4v5M14 18V8h4v10M8 10l3-3 3 2 4-5" />
    </svg>
  );
}

function ProgramCard({ program, index }: { program: Program; index: number }) {
  const visual = categoryVisuals[program.category] ?? { accent: "#0755b9", mark: "EDU" };
  const accentStyle = { "--program-accent": visual.accent } as CSSProperties;

  return (
    <article className={`card hover ${styles.programCard}`} style={accentStyle}>
      <div className={styles.courseVisual} aria-hidden="true">
        <div className={styles.visualTopline}>
          <span>EduSphere Learning Track</span>
          <span>{String(index + 1).padStart(2, "0")}</span>
        </div>
        <div className={styles.courseMark}>{visual.mark}</div>
        <div className={styles.topicRail}>
          {program.curriculum.slice(0, 3).map((topic) => (
            <span key={topic}>{topic}</span>
          ))}
        </div>
      </div>

      <div className={styles.cardBody}>
        <span className={styles.categoryPill}>{program.category}</span>
        <h3>{program.title}</h3>
        <p className={styles.summary}>{program.summary}</p>

        <dl className={styles.factGrid}>
          <div>
            <dt><FactIcon kind="duration" /> Duration</dt>
            <dd>{program.duration}</dd>
          </div>
          <div>
            <dt><FactIcon kind="certificate" /> Outcome</dt>
            <dd>Certificate</dd>
          </div>
          <div>
            <dt><FactIcon kind="placement" /> Career</dt>
            <dd>Placement Support</dd>
          </div>
        </dl>

        <div className={styles.priceRow}>
          <div>
            <span>Programme Fee</span>
            <data value={program.fees}>{feeFormatter.format(Number(program.fees))}</data>
          </div>
          <Link className={styles.exploreLink} href={`/it/programs/${program.slug}`}>
            View Curriculum <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </div>

      <div className={styles.cardStrip}>
        <span>{program.trainer_name}</span>
        <Link href={`/it/contact?program=${program.slug}`}>Request Details</Link>
      </div>
    </article>
  );
}

export default function ProgramCatalogue({
  programs,
  unavailable = false,
  initialCategory = "",
  initialQuery = "",
  initialSort = "title-asc",
  initialPage = 1,
}: {
  programs: Program[];
  unavailable?: boolean;
  initialCategory?: string;
  initialQuery?: string;
  initialSort?: string;
  initialPage?: number;
}) {
  const allowedSorts: SortOption[] = ["title-asc", "fee-asc", "fee-desc", "duration-asc"];
  const [category, setCategory] = useState(initialCategory);
  const [query, setQuery] = useState(initialQuery);
  const [sort, setSort] = useState<SortOption>(allowedSorts.includes(initialSort as SortOption) ? initialSort as SortOption : "title-asc");
  const [page, setPage] = useState(initialPage);

  const categories = useMemo(
    () => Array.from(new Set(programs.map((program) => program.category))).sort((left, right) => left.localeCompare(right)),
    [programs],
  );

  const shown = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const matching = programs.filter((program) => {
      if (category && program.category !== category) return false;
      if (!normalizedQuery) return true;
      return [program.title, program.summary, program.category, program.duration, program.eligibility, program.trainer_name, ...program.curriculum]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
    });

    return matching.toSorted((left, right) => {
      if (sort === "fee-asc") return Number(left.fees) - Number(right.fees);
      if (sort === "fee-desc") return Number(right.fees) - Number(left.fees);
      if (sort === "duration-asc") return durationInWeeks(left.duration) - durationInWeeks(right.duration);
      return left.title.localeCompare(right.title, undefined, { sensitivity: "base" });
    });
  }, [category, programs, query, sort]);

  const totalPages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = shown.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const hasActiveControls = Boolean(category || query.trim() || sort !== "title-asc");

  function applyState(next: Partial<CatalogueState>) {
    const state: CatalogueState = {
      category: next.category ?? category,
      query: next.query ?? query,
      sort: next.sort ?? sort,
      page: next.page ?? page,
    };
    if (next.category !== undefined) setCategory(next.category);
    if (next.query !== undefined) setQuery(next.query);
    if (next.sort !== undefined) setSort(next.sort);
    if (next.page !== undefined) setPage(next.page);
    updateCatalogueUrl(state);
  }

  function clearControls() {
    const state: CatalogueState = { category: "", query: "", sort: "title-asc", page: 1 };
    setCategory(state.category);
    setQuery(state.query);
    setSort(state.sort);
    setPage(state.page);
    updateCatalogueUrl(state);
  }

  if (unavailable) {
    return (
      <div className={styles.emptyState} role="status">
        <span className={styles.emptyMark} aria-hidden="true">!</span>
        <h3>Programme Catalogue Unavailable</h3>
        <p>Programme information could not be loaded. Try again shortly or request details from the training team.</p>
        <Link className="btn" href="/it/contact">Request Programme Details</Link>
      </div>
    );
  }

  if (programs.length === 0) {
    return (
      <div className={styles.emptyState} role="status">
        <span className={styles.emptyMark} aria-hidden="true">+</span>
        <h3>New Programmes Are Being Prepared</h3>
        <p>Published training programmes will appear here. You can still tell us what you want to learn.</p>
        <Link className="btn" href="/it/contact">Request a Callback</Link>
      </div>
    );
  }

  return (
    <div className={styles.catalogue}>
      <nav className={styles.categoryTabs} aria-label="Programme categories">
        <button type="button" className={!category ? styles.activeTab : undefined} aria-pressed={!category} onClick={() => applyState({ category: "", page: 1 })}>
          All Programmes <span>{programs.length}</span>
        </button>
        {categories.map((item) => {
          const count = programs.filter((program) => program.category === item).length;
          return (
            <button type="button" key={item} className={category === item ? styles.activeTab : undefined} aria-pressed={category === item} onClick={() => applyState({ category: item, page: 1 })}>
              {item} <span>{count}</span>
            </button>
          );
        })}
      </nav>

      <div className={styles.catalogueControls} aria-label="Programme catalogue controls">
        <div className={styles.searchField}>
          <label htmlFor="programme-search">Search Programmes</label>
          <div className={styles.searchInputWrap}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>
            <input
              id="programme-search"
              name="q"
              type="search"
              autoComplete="off"
              placeholder="Search Python, SAP, AI, cloud, data…"
              value={query}
              onChange={(event) => applyState({ query: event.target.value, page: 1 })}
            />
          </div>
        </div>
        <div className={styles.sortField}>
          <label htmlFor="programme-sort">Sort By</label>
          <select id="programme-sort" name="sort" value={sort} onChange={(event) => applyState({ sort: event.target.value as SortOption, page: 1 })}>
            <option value="title-asc">Programme A–Z</option>
            <option value="duration-asc">Shortest Duration</option>
            <option value="fee-asc">Fee: Low to High</option>
            <option value="fee-desc">Fee: High to Low</option>
          </select>
        </div>
        {hasActiveControls ? <button className={styles.clearButton} type="button" onClick={clearControls}>Clear Controls</button> : null}
      </div>

      <div className={styles.resultSummary} aria-live="polite">
        <span>{shown.length} {shown.length === 1 ? "programme" : "programmes"}</span>
        {category ? <strong>{category}</strong> : <span>All skill areas</span>}
      </div>

      {pageItems.length > 0 ? (
        <div className={styles.programGrid}>
          {pageItems.map((program, index) => (
            <div className={styles.catalogueItem} key={program.id}>
              <ProgramCard program={program} index={(currentPage - 1) * PAGE_SIZE + index} />
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.emptyState} role="status">
          <span className={styles.emptyMark} aria-hidden="true">?</span>
          <h3>No Matching Programmes</h3>
          <p>Try another skill, choose a different category, or clear the catalogue controls.</p>
          <button className="btn secondary" type="button" onClick={clearControls}>Show All Programmes</button>
        </div>
      )}

      {shown.length > PAGE_SIZE ? (
        <nav className={styles.pagination} aria-label="Programmes pagination">
          <button type="button" disabled={currentPage === 1} onClick={() => applyState({ page: Math.max(1, currentPage - 1) })}>Previous</button>
          <span>Page <strong>{currentPage}</strong> of {totalPages}</span>
          <button type="button" disabled={currentPage === totalPages} onClick={() => applyState({ page: Math.min(totalPages, currentPage + 1) })}>Next</button>
        </nav>
      ) : null}
    </div>
  );
}
