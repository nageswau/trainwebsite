import Image from "next/image";
import Link from "next/link";
import InfoTip from "@/components/InfoTip";
import PublicShell from "@/components/PublicShell";

const svg = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

const ICONS = {
  database: <svg {...svg}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></svg>,
  cap: <svg {...svg}><path d="M21.42 10.92a1 1 0 0 0-.02-1.84L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/></svg>,
  briefcase: <svg {...svg}><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>,
  globe: <svg {...svg}><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>,
  file: <svg {...svg}><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>,
  passport: <svg {...svg}><rect x="4" y="2" width="16" height="20" rx="2"/><circle cx="12" cy="10" r="3.5"/><path d="M8.5 10h7"/><path d="M9 17h6"/></svg>,
};

type Point = { icon: keyof typeof ICONS; tone: "purple" | "green" | "orange" | "red"; text: string; tip: string };

function Points({ prefix, items }: { prefix: string; items: Point[] }) {
  return (
    <ul className="feature-list">
      {items.map((p, i) => (
        <li key={p.text}>
          <span className={`feature-li-icon tone-${p.tone}`}>{ICONS[p.icon]}</span>
          <span>{p.text}</span>
          <InfoTip id={`${prefix}-tip-${i}`} text={p.tip} />
        </li>
      ))}
    </ul>
  );
}

const IT_POINTS: Point[] = [
  { icon: "database", tone: "purple", text: "Full-stack, data, SAP, cloud, AI, cyber security and DevOps", tip: "Explore industry-relevant IT training programs" },
  { icon: "cap", tone: "green", text: "Student and trainer learning portals", tip: "Access student and trainer portals" },
  { icon: "briefcase", tone: "orange", text: "Placement, HR and hiring workflows", tip: "Placement support and hiring workflows" },
];

const OVERSEAS_POINTS: Point[] = [
  { icon: "globe", tone: "red", text: "Country and university discovery", tip: "Explore countries and universities" },
  { icon: "file", tone: "purple", text: "Application and document tracking", tip: "Track your application and documents" },
  { icon: "passport", tone: "green", text: "Visa, appointment and counselor workflows", tip: "Visa guidance and appointment support" },
];

export default function HomePage() {
  return (
    <PublicShell>
      <section className="section">
        <div className="container">
          <div className="grid two">
            <article className="card vertical-card hover">
              <div className="feature-head">
                <Image className="feature-tile" src="/home/it-placement.png" width={192} height={187} alt="" aria-hidden="true" />
                <div>
                  <h2>IT Training & Placement</h2>
                  <p className="lead">Build industry-ready skills through professional IT training and secure placement support with hiring partners.</p>
                </div>
              </div>
              <Points prefix="it" items={IT_POINTS} />
              <Link className="btn" href="/it">Explore IT Training</Link>
            </article>
            <article className="card vertical-card hover">
              <div className="feature-head">
                <span className="feature-tile feature-tile-svg" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/></svg>
                </span>
                <div>
                  <h2>Overseas Education</h2>
                  <p className="lead">Study at globally recognised universities with support across admissions, documentation, scholarships, visas and pre-departure preparation.</p>
                </div>
              </div>
              <Points prefix="overseas" items={OVERSEAS_POINTS} />
              <Link className="btn" href="/overseas">Explore Overseas Education</Link>
            </article>
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
