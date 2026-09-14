import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import { publicApi } from "@/lib/api";
import type { CareerPath } from "@/lib/types";

export default async function CareerPathDetail({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let path: CareerPath | null = null;
  try {
    path = await publicApi<CareerPath>(`/api/v1/public/career-paths/${slug}`);
  } catch {}

  if (!path) {
    return (
      <PublicShell division="it">
        <section className="section">
          <div className="container">
            <h1>Career path not found</h1>
            <Link className="btn" href="/it/career-paths">Back to career paths</Link>
          </div>
        </section>
      </PublicShell>
    );
  }

  return (
    <PublicShell division="it">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">Career Path</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{path.title}</h1>
          <p className="lead">{path.summary}</p>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <h3>Skills you&apos;ll build</h3>
            <ul className="list-clean">
              {path.skills.map((skill) => (
                <li key={skill}>{skill}</li>
              ))}
            </ul>
          </div>
          {path.related_program_slugs.length > 0 && (
            <div className="card" style={{ marginTop: 18 }}>
              <h3>Related programs</h3>
              <ul className="list-clean">
                {path.related_program_slugs.map((programSlug) => (
                  <li key={programSlug}>
                    <Link href={`/it/programs/${programSlug}`}>{programSlug.replaceAll("-", " ")}</Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="card" style={{ marginTop: 18 }}>
            <h3>Career outcomes</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{path.outcomes}</p>
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
