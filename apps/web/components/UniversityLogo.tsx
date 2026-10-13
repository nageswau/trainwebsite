// dtu-001: the university's logo (from its official site), or a monogram tile when there is none.
// `decorative` is for a logo beside the university's own name as a heading (the name already says it).
// The tile stays white in dark mode too: some logos are dark on transparent.
export default function UniversityLogo({ name, logoUrl, size = 48, decorative = false }: { name: string; logoUrl: string | null | undefined; size?: number; decorative?: boolean }) {
  const box = { width: size, height: size, borderRadius: 8, flex: "none" } as const;
  // eslint-disable-next-line @next/next/no-img-element -- a small static/remote tile; next/image would need remote host config for every logo URL
  if (logoUrl) return <img src={logoUrl} alt={decorative ? "" : `${name} logo`} width={size} height={size} loading="lazy" style={{ ...box, objectFit: "contain", background: "#fff" }} />;
  const initials = name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("") || name.slice(0, 1).toUpperCase();
  return <span {...(decorative ? { "aria-hidden": true } : { "aria-label": name, role: "img" })} style={{ ...box, display: "inline-grid", placeItems: "center", fontWeight: 700, background: "var(--surface-2, #eef1f6)" }}>{initials}</span>;
}
