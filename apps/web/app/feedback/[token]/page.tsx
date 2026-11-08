import type { Metadata } from "next";

import PlacementSurveyForm from "@/components/PlacementSurveyForm";
import PublicShell from "@/components/PublicShell";

// pob-026 (DEC-SCOPE-435 S12): the no-login satisfaction survey. Outside every protected prefix; the signed link is the credential, so the
// page is never indexed and never sends its URL (the token) on as a referrer.
export const metadata: Metadata = { title: "Your feedback", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default async function FeedbackPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <PublicShell showLogin={false}>
      <section className="section">
        <div className="container" style={{ maxWidth: 640 }}>
          <PlacementSurveyForm token={token} />
        </div>
      </section>
    </PublicShell>
  );
}
