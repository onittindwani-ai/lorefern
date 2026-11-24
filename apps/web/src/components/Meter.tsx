/** Two small bars under an answer: how well the search matched, and how well each sentence is backed by its source. */
export function Meter({ retrieval, groundedness }: { retrieval: number; groundedness: number }) {
  const pct = (n: number) => `${Math.max(0, Math.min(100, Math.round(n * 100)))}%`;
  return (
    <div className="cx-meter" aria-label="How well this answer is backed">
      <div className="cx-meter__bars">
        <div>
          <span className="cx-mini">Search match {pct(retrieval)}</span>
          <div className="cx-bar" role="progressbar" aria-label="Search match" aria-valuenow={Math.round(retrieval * 100)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: pct(retrieval) }} /></div>
        </div>
        <div>
          <span className="cx-mini">Backed by the source {pct(groundedness)}</span>
          <div className="cx-bar" role="progressbar" aria-label="Backed by the source" aria-valuenow={Math.round(groundedness * 100)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: pct(groundedness) }} /></div>
        </div>
      </div>
    </div>
  );
}
