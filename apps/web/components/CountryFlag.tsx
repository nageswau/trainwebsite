import { flagSrc } from "@/lib/countryFlag";

// PUB-023 (DEC-SCOPE-222): a decorative flag before a country name (F4: the name is always beside it, so alt="" + aria-hidden).
// Server-safe (no state or effects) so public pages stay server-rendered; renders nothing without a valid code (F3).
const SIZES = { inline: [20, 15], large: [40, 30] } as const;
export type FlagSize = keyof typeof SIZES;

export default function CountryFlag({ iso2, size = "inline" }: { iso2: string | null | undefined; size?: FlagSize }) {
  const src = flagSrc(iso2);
  if (!src) return null;
  const [width, height] = SIZES[size];
  // eslint-disable-next-line @next/next/no-img-element -- a small static local SVG; next/image would need dangerouslyAllowSVG
  return <img className={`country-flag country-flag--${size}`} src={src} alt="" aria-hidden="true" width={width} height={height} loading="lazy" decoding="async" />;
}
