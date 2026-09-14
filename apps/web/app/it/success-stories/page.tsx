import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import { publicApi } from "@/lib/api";
import type { Testimonial } from "@/lib/types";

export default async function SuccessStories() {
  let stories: Testimonial[] = [];
  try {
    stories = await publicApi<Testimonial[]>("/api/v1/public/testimonials?division=it");
  } catch {}

  const items = stories.map((story) => ({
    id: story.id,
    searchText: `${story.person_name} ${story.headline} ${story.quote}`,
    sortValues: { name: story.person_name },
    content: (
      <article className="card" key={story.id}>
        <h3>{story.headline}</h3>
        <p className="muted">&ldquo;{story.quote}&rdquo;</p>
        <p style={{ fontSize: 13 }}>— {story.person_name}</p>
        <Link className="btn small" href={`/it/success-stories/${story.id}`}>Read story</Link>
      </article>
    ),
  }));

  return (
    <PublicShell division="it">
      <PageHero
        eyebrow="Success Stories"
        title="Real learners, real outcomes"
        description="Hear directly from EduSphere learners about their training and placement experience."
      />
      <section className="section">
        <div className="container">
          <CollectionExplorer
            items={items}
            noun="stories"
            searchPlaceholder="Search success stories…"
            sorts={[{ value: "name", key: "name", label: "Name A–Z" }]}
            empty={
              <div className="card">
                <h3>No success stories published yet</h3>
                <p className="muted">Administrators can publish testimonials through the CMS.</p>
              </div>
            }
          />
        </div>
      </section>
    </PublicShell>
  );
}
