import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import { publicApi } from "@/lib/api";
import type { ContentPage } from "@/lib/types";

export default async function BusinessServices() {
  let page: ContentPage | null = null;
  try {
    page = await publicApi<ContentPage>("/api/v1/cms/pages/it/business-services");
  } catch {}

  return (
    <PublicShell division="it">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">Business Services</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{page?.title || "Business Services"}</h1>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <p style={{ whiteSpace: "pre-wrap" }}>
              {page?.body || "Corporate training and staffing services information is not yet published."}
            </p>
            <Link className="btn" href="/it/contact" style={{ marginTop: 18, display: "inline-block" }}>
              Talk to our business team
            </Link>
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
