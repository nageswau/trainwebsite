// PUB-023 (DEC-SCOPE-222): a country's flag is the bundled /flags/<iso2>.svg. Only a two-letter code is ever turned into a path,
// so nothing else (empty, three letters, "../x") can reach the URL; null means "show no flag" (F3).
const CODE = /^[A-Za-z]{2}$/;

export function flagSrc(iso2: string | null | undefined): string | null {
  const code = (iso2 ?? "").trim();
  return CODE.test(code) ? `/flags/${code.toLowerCase()}.svg` : null;
}
