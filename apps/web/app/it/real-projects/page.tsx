import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import { publicApi } from "@/lib/api";
import type { RealProject } from "@/lib/types";

export default async function RealProjects() {
  let projects: RealProject[] = [];
  try {
    projects = await publicApi<RealProject[]>("/api/v1/public/real-projects?division=it");
  } catch {}

  const items = projects.map((project) => ({
    id: project.id,
    searchText: `${project.title} ${project.summary} ${project.tech_stack.join(" ")}`,
    sortValues: { title: project.title },
    content: (
      <article className="card" key={project.id}>
        <h3>{project.title}</h3>
        <p className="muted">{project.summary}</p>
        <p style={{ fontSize: 13 }}>{project.tech_stack.join(" · ")}</p>
        <Link className="btn small" href={`/it/real-projects/${project.slug}`}>View project</Link>
      </article>
    ),
  }));

  return (
    <PublicShell division="it">
      <PageHero
        eyebrow="Real Projects"
        title="Build a portfolio employers can actually verify"
        description="Real-world project examples learners build during training, with the tech stack and scope described in full."
      />
      <section className="section">
        <div className="container">
          <CollectionExplorer
            items={items}
            noun="projects"
            searchPlaceholder="Search real projects…"
            sorts={[{ value: "title", key: "title", label: "Title A–Z" }]}
            empty={
              <div className="card">
                <h3>No projects published yet</h3>
                <p className="muted">Administrators can publish real-world projects through the CMS.</p>
              </div>
            }
          />
        </div>
      </section>
    </PublicShell>
  );
}
