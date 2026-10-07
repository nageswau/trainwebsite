// An ⓘ button whose tooltip shows on hover and on keyboard focus (CSS only, so it works in
// server components). The text is wired with aria-describedby, so screen readers announce it
// even while the bubble is visually hidden. `id` must be unique on the page.
export default function InfoTip({ id, text }: { id: string; text: string }) {
  return (
    <span className="info-tip">
      <button type="button" className="info-tip-btn" aria-label="More info" aria-describedby={id}>i</button>
      <span role="tooltip" id={id} className="info-tip-bubble">{text}</span>
    </span>
  );
}
