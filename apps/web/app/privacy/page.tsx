import type { Metadata } from "next";
import Link from "next/link";

import PageHero from "@/components/PageHero";
import PublicShell from "@/components/PublicShell";
import { OFFICES } from "@/lib/offices";
import { PENDING_FACTS, POLICY_FACTS, type PolicyFact, POLICY_UPDATED } from "@/lib/privacyPolicy";

// PUB-026 (DEC-SCOPE-442): the public privacy policy. Ads, lead forms (Meta lead ads need a privacy policy URL) and every
// form on the site link here. Each statement describes what the product actually does today; facts EduSphere has not
// confirmed come from `lib/privacyPolicy.ts` and show as "to be confirmed" until filled in.

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How EduSphere collects, uses, shares and protects your personal data, and how to exercise your rights.",
  alternates: { canonical: "/privacy" },
};

function Fact({ fact, email = false }: { fact: PolicyFact; email?: boolean }) {
  if (!fact.value) return <mark className="pending">[To be confirmed: {fact.label.toLowerCase()}]</mark>;
  return email ? <a href={`mailto:${fact.value}`}>{fact.value}</a> : <>{fact.value}</>;
}

const SECTIONS = [
  ["who-we-are", "Who we are"],
  ["what-we-collect", "What we collect"],
  ["how-we-use", "How we use it"],
  ["sharing", "Who we share it with"],
  ["cookies", "Cookies and analytics"],
  ["retention", "How long we keep it"],
  ["security", "How we protect it"],
  ["rights", "Your rights"],
  ["children", "Children"],
  ["changes", "Changes to this policy"],
  ["contact", "Contact and complaints"],
] as const;

export default function PrivacyPolicy() {
  return (
    <PublicShell>
      <PageHero
        eyebrow="Legal"
        title="Privacy Policy"
        description="How EduSphere collects, uses and protects your personal data when you visit our website, respond to our adverts, enquire about a course or study abroad, or use our portals."
      />
      <section className="section compact">
        <div className="container prose" style={{ maxWidth: 820 }}>
          <p className="muted">Last updated: {POLICY_UPDATED}</p>

          {PENDING_FACTS.length > 0 && (
            <aside className="card" role="note" aria-label="Details still to be confirmed">
              <strong>Draft:</strong> some details in this policy are still being confirmed and are marked below.
            </aside>
          )}

          <nav aria-label="On this page">
            <ol>
              {SECTIONS.map(([id, title]) => (
                <li key={id}><a href={`#${id}`}>{title}</a></li>
              ))}
            </ol>
          </nav>

          <h2 id="who-we-are">1. Who we are</h2>
          <p>
            EduSphere provides IT training and placement support, and overseas education guidance. In this policy, &ldquo;EduSphere&rdquo;,
            &ldquo;we&rdquo; and &ldquo;us&rdquo; means <Fact fact={POLICY_FACTS.legalEntity} />. We decide why and how your personal data is
            used, so we are the data fiduciary under India&rsquo;s Digital Personal Data Protection Act, 2023, and the controller under the UK
            GDPR where it applies to you.
          </p>
          <p>Our offices:</p>
          <ul>
            {OFFICES.map((office) => (
              <li key={office.city}><strong>{office.city}:</strong> {office.address}</li>
            ))}
          </ul>

          <h2 id="what-we-collect">2. What we collect</h2>
          <ul>
            <li>
              <strong>Enquiries and lead forms:</strong> your name, email address, phone number (optional on our website), the course or
              service you are interested in and your message. This includes forms on our website and lead forms inside our adverts on
              Facebook and Instagram, where Meta passes us the details you entered.
            </li>
            <li>
              <strong>Where you came from:</strong> the source of your enquiry (for example Instagram, Facebook, Google, our website, WhatsApp
              or a walk-in). For job applications and candidate sign-ups we also record the campaign tags in the link you followed.
            </li>
            <li>
              <strong>Conversations with our team:</strong> notes of calls, WhatsApp messages, emails and meetings with our counsellors and
              advisers, and follow-ups about your enquiry.
            </li>
            <li>
              <strong>Event registrations:</strong> your name, email address and phone number when you register for a webinar or event.
            </li>
            <li>
              <strong>Students and applicants:</strong> if you enrol or apply, the details needed to deliver the service, such as your
              education history, test scores, documents you upload (for example transcripts, passport and visa documents for overseas
              applications), course enrolments, attendance, assessments and payments.
            </li>
            <li>
              <strong>Job seekers and candidates:</strong> if you apply for a job or join our placement candidate pool, your CV, skills,
              experience and the consent you gave.
            </li>
            <li>
              <strong>Accounts:</strong> your sign-in details and a record of important actions taken in our portals.
            </li>
          </ul>
          <p>
            We do not ask for sensitive details such as your marks, phone number or finances in public comments on our social media posts.
            Please share them only through our forms or directly with your adviser.
          </p>

          <h2 id="how-we-use">3. How we use it</h2>
          <ul>
            <li>To reply to your enquiry and give you the course, admission, visa or placement guidance you asked for.</li>
            <li>To contact you by phone, WhatsApp, SMS or email about your enquiry, application or course.</li>
            <li>To enrol you, run your classes, process applications to universities on your behalf, and take payments.</li>
            <li>To share your profile with employers, but only when you have joined the candidate pool and agreed to it.</li>
            <li>To understand which adverts and pages work, using website analytics and the source of each enquiry.</li>
            <li>To keep our services secure, prevent fraud and meet our legal, tax and accounting obligations.</li>
          </ul>
          <p>
            We rely on your consent when you submit a form or join the candidate pool, and on what is needed to deliver the service you
            asked for. You can withdraw your consent at any time (see <a href="#rights">Your rights</a>). Withdrawing does not affect
            anything we did before you withdrew it.
          </p>
          <p>We do not sell your personal data.</p>

          <h2 id="sharing">4. Who we share it with</h2>
          <ul>
            <li><strong>Universities and colleges</strong> you ask us to apply to, with the documents needed for the application.</li>
            <li><strong>Employers</strong>, only for candidates who have agreed to share their profile.</li>
            <li>
              <strong>Service providers</strong> who process data for us under our instructions: cloud hosting and database (DigitalOcean),
              email delivery (Zoho Mail), SMS and WhatsApp messaging (Twilio), online payments (Razorpay) and website analytics (Google
              Analytics).
            </li>
            <li><strong>Advertising platforms:</strong> Meta receives the details you enter into a lead form inside one of our adverts.</li>
            <li><strong>Authorities</strong> when the law requires it.</li>
          </ul>
          <p>
            Some of these providers may store or process data outside the country you live in. Where that happens we rely on the safeguards
            the law requires for such transfers.
          </p>

          <h2 id="cookies">5. Cookies and analytics</h2>
          <ul>
            <li>
              <strong>Sign-in cookies</strong> (<code>edusphere_access</code>, <code>edusphere_refresh</code>) keep you signed in to our
              portals. They are strictly necessary and are set only when you sign in.
            </li>
            <li>
              <strong>Your cookie choice</strong> (<code>edusphere_consent</code>) remembers whether you accepted analytics cookies, for 6
              months. It is strictly necessary.
            </li>
            <li>
              <strong>Google Analytics</strong> cookies (<code>_ga</code>, <code>_ga_*</code>) count visits and show which pages are used.
              They are set only if you click &ldquo;Accept analytics&rdquo; on our cookie banner. We ask Google to anonymise your IP
              address, and we never send it the address of password-reset pages.
            </li>
          </ul>
          <p>
            You can change your choice at any time with &ldquo;Cookie settings&rdquo; at the bottom of every page. If you reject analytics
            cookies, we delete the Google Analytics cookies already set.
          </p>
          <p>We do not use the Meta Pixel or other advertising cookies on this website.</p>

          <h2 id="retention">6. How long we keep it</h2>
          <p>
            We keep personal data only for as long as we need it for the purpose it was collected for, or as long as the law requires.
            Enquiries and leads that do not lead to an enrolment are kept for <Fact fact={POLICY_FACTS.leadRetention} />. Records we must
            keep by law, such as payment and tax records, are kept for the period the law sets, even if you ask us to delete your account.
          </p>

          <h2 id="security">7. How we protect it</h2>
          <p>
            Access to personal data is limited by role, so staff see only what their work needs. Uploaded documents are stored privately
            and are not publicly reachable. Data is encrypted in transit, and important changes are recorded in an audit log.
          </p>

          <h2 id="rights">8. Your rights</h2>
          <p>Depending on where you live, you can ask us to:</p>
          <ul>
            <li>tell you what personal data we hold about you and give you a copy;</li>
            <li>correct or complete it;</li>
            <li>delete it, unless we must keep it by law;</li>
            <li>stop contacting you for marketing, or withdraw your consent;</li>
            <li>object to or restrict how we use it (UK);</li>
            <li>nominate someone to act for you if you die or become unable to (India).</li>
          </ul>
          <p>
            If you have an account, you can download your data or ask for it to be deleted yourself from{" "}
            <Link href="/account/privacy">Privacy &amp; your data</Link>. Otherwise, or for anything else, contact us using the details
            below. We will reply within the time the law allows.
          </p>

          <h2 id="children">9. Children</h2>
          <p>
            Some of our services are used by students under 18. If you are under 18, please ask a parent or guardian to contact us with
            you. A parent or guardian can exercise the rights in this policy on a child&rsquo;s behalf.
          </p>

          <h2 id="changes">10. Changes to this policy</h2>
          <p>
            We will update this page when the way we handle personal data changes, and change the &ldquo;Last updated&rdquo; date at the
            top.
          </p>

          <h2 id="contact">11. Contact and complaints</h2>
          <ul>
            <li>Privacy questions and requests: <Fact fact={POLICY_FACTS.privacyContact} email /></li>
            <li>Grievance officer: <Fact fact={POLICY_FACTS.grievanceOfficer} />, at the same address</li>
          </ul>
          <p>
            If you are not satisfied with our reply, you can complain to the Data Protection Board of India or, in the UK, to the
            Information Commissioner&rsquo;s Office (<a href="https://ico.org.uk/make-a-complaint/" rel="noopener noreferrer">ico.org.uk</a>).
          </p>
        </div>
      </section>
    </PublicShell>
  );
}
