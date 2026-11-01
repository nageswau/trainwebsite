import type { Program } from "@/lib/types";

import styles from "./ProgramSyllabus.module.css";

// PUB-025 (DEC-SCOPE-334): a course's ONE syllabus source (S1), open to everyone with no enquiry gate (S2). With no syllabus set, the
// course's curriculum list is shown as before.
export default function ProgramSyllabus({ program }: { program: Program }) {
  const syllabus = program.syllabus;

  if (!syllabus) {
    return (
      <>
        <h2>Curriculum</h2>
        <ol>{program.curriculum.map((topic) => <li key={topic} style={{ padding: "8px 0" }}>{topic}</li>)}</ol>
      </>
    );
  }

  if (syllabus.source === "manual") {
    return (
      <>
        <h2>Syllabus</h2>
        <div className={styles.modules}>
          {syllabus.modules.map((module, index) => (
            <details key={`${index}-${module.title}`} className={styles.module} open={index === 0}>
              <summary>
                <span className={styles.moduleNumber}>{String(index + 1).padStart(2, "0")}</span>
                <span className={styles.moduleTitle}>{module.title}</span>
                {module.topics.length > 0 ? <span className={styles.topicCount}>{`${module.topics.length} ${module.topics.length === 1 ? "topic" : "topics"}`}</span> : null}
              </summary>
              {module.topics.length > 0 ? <ul>{module.topics.map((topic, t) => <li key={`${t}-${topic}`}>{topic}</li>)}</ul> : null}
            </details>
          ))}
        </div>
      </>
    );
  }

  const isPdf = syllabus.source === "pdf";
  return (
    <>
      <h2>Syllabus</h2>
      <div className={styles.download}>
        <span className={styles.fileMark} aria-hidden="true">{isPdf ? "PDF" : "↗"}</span>
        <div>
          <strong>{program.title} syllabus</strong>
          <p className="muted">{isPdf ? "The full module-by-module syllabus as a PDF." : "The full module-by-module syllabus, opens in a new tab."}</p>
        </div>
        <a className="btn" href={syllabus.url} target="_blank" rel="noopener noreferrer">
          {isPdf ? "Download syllabus (PDF)" : "Open syllabus"}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </div>
    </>
  );
}
