"use client";

import CollectionExplorer from "./CollectionExplorer";

type Faq = {category: string; q: string; a: string};
const faqs: Faq[] = [
  {category: "Admissions", q: "How do I enrol in an EduSphere IT program?", a: "Choose a program, submit a training enquiry, complete counseling and eligibility review, then confirm your batch and fee plan."},
  {category: "Training", q: "Where do I access live classes and recordings?", a: "IT students receive live session links, recordings, notes, assignments and downloads from their Student Portal after enrolment."},
  {category: "Payments", q: "Can course fees be paid in instalments?", a: "Where an EMI plan is approved for a program, the Student Portal shows instalment due dates, pending balance, receipts and payment status."},
  {category: "Certificates", q: "When is my IT training certificate issued?", a: "Certificates are issued after the configured completion criteria are met, such as attendance, assignments and assessments."},
  {category: "Placements", q: "Does EduSphere guarantee placement?", a: "The platform supports resume building, mock interviews, referrals, drives and placement tracking. Any commercial placement commitment should follow the signed program terms."},
  {category: "Overseas", q: "How does the overseas admission process work?", a: "The workflow covers profile evaluation, destination and university selection, application, offer, financial documentation, visa preparation, travel support and pre-departure orientation."},
  {category: "Overseas", q: "Can I track my university applications online?", a: "Yes. Overseas students can see applications, documents, offer letters, visa progress, appointments, payments and counselor communication in the Overseas Student Portal."},
  {category: "Visa", q: "Does EduSphere decide visa outcomes?", a: "No. EduSphere can support documentation, preparation and tracking, but visa decisions are made by the relevant government or immigration authority."},
];

export default function FaqSearch() {
  const items = faqs.map((faq, index) => ({
    id: String(index), searchText: `${faq.q} ${faq.a} ${faq.category}`, filters: {category: faq.category}, sortValues: {question: faq.q, category: faq.category},
    content: <details><summary><span className="badge" style={{marginRight: 10}}>{faq.category}</span>{faq.q}</summary><p>{faq.a}</p></details>,
  }));
  return <CollectionExplorer items={items} noun="questions" searchPlaceholder="Search admissions, training, payments, certificates, visas…" filters={[{key: "category", label: "Category"}]} sorts={[{value: "question", key: "question", label: "Question A–Z"}, {value: "category", key: "category", label: "Category A–Z"}]} layoutClassName="faq card" initialPageSize={6} empty={<div className="card"><h3>No questions available</h3><p className="muted">Contact the relevant EduSphere team for support.</p><a className="btn" href="/contact">Contact support</a></div>}/>;
}
