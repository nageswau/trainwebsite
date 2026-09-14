export const SUPPORTED_LOCALES=["en-GB"] as const;
export type SupportedLocale=typeof SUPPORTED_LOCALES[number];
export const DEFAULT_LOCALE:SupportedLocale="en-GB";
// Add translation dictionaries and locale-prefixed routes here when a second language is approved.
