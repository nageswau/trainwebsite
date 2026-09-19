import Script from "next/script";

// ENH-003 security review S1: `gtag('config')` reports the full page URL, query string included.
// A set-password / reset link carries a live credential in its query string, so those pages are
// never configured -- and therefore never reported to Google.
export function gaInlineScript(id: string): string {
  return `window.dataLayer=window.dataLayer||[]
function gtag(){dataLayer.push(arguments)}
gtag('js',new Date())
if(!/\\/reset-password(\\/|$)/.test(window.location.pathname)){gtag('config','${id}',{anonymize_ip:true})}
`;
}

export default function Analytics() {
  const id = process.env.NEXT_PUBLIC_GA_ID;
  if (!id) return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${id}`} strategy="afterInteractive" />
      <Script id="ga" strategy="afterInteractive">{gaInlineScript(id)}</Script>
    </>
  );
}
