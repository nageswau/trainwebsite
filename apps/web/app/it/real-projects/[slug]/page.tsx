import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import { publicApi } from "@/lib/api";
import type { RealProject } from "@/lib/types";

export default async function RealProjectDetail({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let project: RealProject | null = null;
  try {
    project = await publicApi<RealProject>(`/api/v1/public/real-projects/${slug}`);
  } catch {}

  if (!project) {
    return (
      <PublicShell division="it">
        <section className="section">
          <div className="container">
            <h1>Project not found</h1>
            <Link className="btn" href="/it/real-projects">Back to real projects</Link>
          </div>
        </section>
      </PublicShell>
    );
  }

  return (
    <PublicShell division="it">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">Real Project</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{project.title}</h1>
          <p className="lead">{project.summary}</p>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <h3>What you&apos;ll build</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{project.description}</p>
          </div>
          <div className="card" style={{ marginTop: 18 }}>
            <h3>Tech stack</h3>
            <ul className="list-clean">
              {project.tech_stack.map((tech) => (
                <li key={tech}>{tech}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
