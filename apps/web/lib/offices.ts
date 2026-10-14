// PUB-024 (DEC-SCOPE-223): EduSphere's offices, as given by the owner on 2026-10-14 (spelling and punctuation tidied only).
// All three serve both IT Training and Overseas Education. The single source for every page that shows them.
export type Office = { city: string; address: string };

export const OFFICES: readonly Office[] = [
  { city: "Bengaluru", address: "#57, B.B. Road, Allasandra Gate, G.K.V.K. Post, Yelahanka, Bengaluru – 560065" },
  { city: "Hyderabad", address: "Shop No. 1, Raja Rajeshwari Residency Apartments, Employees' Colony, Bapuji Nagar Road, Yapral, Hyderabad – 500087" },
  { city: "Tadepalligudem", address: "KK Plaza, 1st Floor, Opp. Sonovision, KN Road, Gollagudem Center, Tadepalligudem, West Godavari District, Andhra Pradesh – 534102" },
];

/** A Google Maps search link for an address: a plain URL, so no API key and no third-party script on our pages. */
export function mapsUrl(address: string): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}
