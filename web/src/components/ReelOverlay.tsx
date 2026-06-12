import { useEffect, useMemo, useState } from "react";
import { posterUrl } from "../lib/tmdb";
import type { Movie } from "../lib/types";

const SPIN_MS = 2200;
const STRIP_REPEATS = 4;

interface ReelOverlayProps {
  /** Posters borrowed from the current results to fill the spinning strip. */
  pool: Movie[];
  /** The actual pick once the API answers; null while in flight. */
  result: Movie | null;
  onDone: (movie: Movie) => void;
  onCancel: () => void;
}

/**
 * Slot-machine moment for "Spin the reel": a vertical strip of posters
 * blurs past, decelerates, and lands on the real pick before the full
 * detail page takes over.
 */
export default function ReelOverlay({ pool, result, onDone, onCancel }: ReelOverlayProps) {
  const [phase, setPhase] = useState<"spinning" | "landed">("spinning");

  // Escape cancels; stray clicks must NOT (easy to fire one right after
  // pressing Spin, which used to silently swallow the whole roll).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const strip = useMemo(() => {
    const posters = pool
      .map((movie) => ({ key: movie.movie_key ?? movie.title, url: posterUrl(movie.poster_path) }))
      .filter((entry): entry is { key: string; url: string } => Boolean(entry.url))
      .slice(0, 8);
    const filler: { key: string; url: string | null }[] =
      posters.length >= 3
        ? posters
        : [
            ...posters,
            ...Array.from({ length: 5 - posters.length }, (_, index) => ({
              key: `blank-${index}`,
              url: null,
            })),
          ];
    return Array.from({ length: STRIP_REPEATS }, () => filler).flat();
  }, [pool]);

  // Land once both the minimum spin time has elapsed AND the result arrived.
  useEffect(() => {
    if (!result) return;
    const remaining = SPIN_MS;
    const timer = setTimeout(() => setPhase("landed"), remaining);
    return () => clearTimeout(timer);
  }, [result]);

  // After the landing beat, hand over to the detail page.
  useEffect(() => {
    if (phase !== "landed" || !result) return;
    const timer = setTimeout(() => onDone(result), 900);
    return () => clearTimeout(timer);
  }, [phase, result, onDone]);

  const landedPoster = result ? posterUrl(result.poster_path, "w500") : null;

  return (
    <div
      className="fixed inset-0 z-[70] flex flex-col items-center justify-center bg-night-950/92 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-label="Spinning the reel"
    >
      <p className="mb-6 animate-pulse text-xs font-medium uppercase tracking-[0.4em] text-gold-400">
        {phase === "spinning" ? "spinning the reel" : "tonight's pick"}
      </p>

      <div className="relative h-[340px] w-[220px] overflow-hidden rounded-2xl ring-1 ring-gold-500/30 shadow-glow">
        {phase === "spinning" ? (
          <div
            className="flex flex-col"
            style={{
              animation: `reelspin ${result ? SPIN_MS : SPIN_MS * 3}ms cubic-bezier(0.15, 0.6, 0.35, 1) ${result ? "" : "infinite"}`,
            }}
          >
            {strip.map((entry, index) => (
              <div key={`${entry.key}-${index}`} className="h-[340px] w-[220px] shrink-0">
                {entry.url ? (
                  <img src={entry.url} alt="" className="h-full w-full object-cover blur-[2px]" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-night-600 via-night-700 to-night-800">
                    <span className="font-display text-5xl font-bold text-gold-500/40">?</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="animate-iris h-full w-full">
            {landedPoster ? (
              <img src={landedPoster} alt={result?.title ?? ""} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-gradient-to-br from-night-600 via-night-700 to-night-800 p-4">
                <span className="font-display text-5xl font-bold text-gold-500/60">
                  {result?.title.slice(0, 1)}
                </span>
                <span className="text-center font-display text-base text-fog-300">
                  {result?.title}
                </span>
              </div>
            )}
          </div>
        )}
        {/* Slot window shading */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-night-950/70 via-transparent to-night-950/70" />
      </div>

      {phase === "landed" && result && (
        <h2 className="animate-rise mt-6 max-w-md text-center font-display text-2xl font-bold text-snow">
          {result.title}
          {result.year ? <span className="ml-2 text-lg font-normal text-fog-400">{result.year}</span> : null}
        </h2>
      )}

      <style>{`
        @keyframes reelspin {
          from { transform: translateY(0); }
          to { transform: translateY(calc(-340px * ${strip.length - 1})); }
        }
      `}</style>
    </div>
  );
}
