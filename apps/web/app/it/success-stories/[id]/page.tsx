import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import { publicApi } from "@/lib/api";
import type { Testimonial } from "@/lib/types";

export default async function SuccessStoryDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let story: Testimonial | null = null;
  try {
    story = await publicApi<Testimonial>(`/api/v1/public/testimonials/${id}`);
  } catch {}

  if (!story) {
    return (
      <PublicShell division="it">
        <section className="section">
          <div className="container">
            <h1>Success story not found</h1>
            <Link className="btn" href="/it/success-stories">Back to success stories</Link>
          </div>
        </section>
      </PublicShell>
    );
  }

  return (
    <PublicShell division="it">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">Success Story</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{story.headline}</h1>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <p className="lead" style={{ whiteSpace: "pre-wrap" }}>&ldquo;{story.quote}&rdquo;</p>
            <p className="muted" style={{ marginTop: 12 }}>— {story.person_name}</p>
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
