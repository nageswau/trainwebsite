"use client";

// tel-001 QA follow-up: on a phone or tablet the admin list comes before its create form (bdm-001 QA-15), so a long list pushes
// the form far down. This link, shown only at those widths (globals.css .create-jump), scrolls to the form and focuses its first
// field. Without JavaScript it is a plain in-page anchor.
export default function CreateJumpLink({ targetId, label }: { targetId: string; label: string }) {
  function jump(event: React.MouseEvent<HTMLAnchorElement>) {
    const target = document.getElementById(targetId);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView?.({ block: "center" });
    target.focus({ preventScroll: true });
  }

  return (
    <a href={`#${targetId}`} className="btn secondary small create-jump" onClick={jump}>
      {label}
    </a>
  );
}
