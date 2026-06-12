import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useLibrary } from "../hooks/useLibrary";
import { useTilt } from "../hooks/useTilt";
import { asList, backdropUrl, posterUrl } from "../lib/tmdb";
import type { Movie } from "../lib/types";

interface MovieDetailProps {
  movie: Movie | null;
  cacheKey?: string | null;
  onClose: () => void;
}

/**
 * Full-page movie view. Clicking a card irises this open over the whole
 * viewport: parallax backdrop, one-sheet typography, library actions and
 * the AI match explanation. Esc or ✕ closes.
 */
export default function MovieDetail({ movie, cacheKey, onClose }: MovieDetailProps) {
  const { isFavorite, watchlistItem, toggleFavorite, toggleWatchlist, toggleWatched } =
    useLibrary();
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const backdropLayer = useRef<HTMLDivElement>(null);
  const tilt = useTilt(5);

  // Explanations stream in after render — they are never on the result path.
  useEffect(() => {
    setExplanation(null);
    if (!movie?.movie_key || !cacheKey) return;
    let cancelled = false;
    setExplaining(true);
    api
      .explain(cacheKey, movie.movie_key)
      .then((response) => {
        if (!cancelled) setExplanation(response.explanation);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setExplaining(false);
      });
    return () => {
      cancelled = true;
    };
  }, [movie?.movie_key, cacheKey]);

  useEffect(() => {
    if (!movie) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    scroller.current?.scrollTo({ top: 0 });
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [movie, onClose]);

  // Parallax: the backdrop drifts at ~1/3 scroll speed behind the content.
  const onScroll = () => {
    const top = scroller.current?.scrollTop ?? 0;
    if (backdropLayer.current) {
      backdropLayer.current.style.transform = `translateY(${top * 0.35}px) scale(1.08)`;
    }
  };

  if (!movie) return null;

  const wideBackdrop = backdropUrl(movie.backdrop_path);
  const backdrop = wideBackdrop ?? posterUrl(movie.poster_path, "w500");
  const ambientBackdrop = !wideBackdrop; // poster fallback gets blurred to ambient fill
  const poster = posterUrl(movie.poster_path, "w500");
  const genres = asList(movie.genres);
  const keywords = asList(movie.keywords).slice(0, 10);
  const moods = movie.film_mood_tags ?? [];
  const favored = isFavorite(movie.movie_key);
  const listed = watchlistItem(movie.movie_key);
  const tmdbHref = movie.tmdb_id ? `https://www.themoviedb.org/movie/${movie.tmdb_id}` : null;

  return (
    <div
      ref={scroller}
      onScroll={onScroll}
      className="animate-iris fixed inset-0 z-[60] overflow-y-auto bg-night-950 scrollbar-none"
      role="dialog"
      aria-modal="true"
      aria-label={movie.title}
    >
      {/* Parallax backdrop layer */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div ref={backdropLayer} className="absolute inset-0 will-change-transform" style={{ transform: "scale(1.08)" }}>
          {backdrop ? (
            ambientBackdrop ? (
              <>
                {/* Ambient color wash from the poster itself */}
                <img
                  src={backdrop}
                  alt=""
                  className="h-full w-full scale-110 object-cover opacity-70 blur-3xl saturate-150"
                />
                {/* The poster, blown up huge and sharp, melting into the dark on its left edge */}
                <img
                  src={posterUrl(movie.poster_path, "w780") ?? backdrop}
                  alt=""
                  className="animate-kenburns absolute right-[-6%] top-1/2 h-[124%] max-w-none -translate-y-1/2 rounded-3xl object-cover opacity-95 shadow-[0_0_120px_rgba(0,0,0,0.9)]"
                  style={{
                    maskImage:
                      "linear-gradient(to left, black 45%, rgba(0,0,0,0.55) 72%, transparent 98%)",
                    WebkitMaskImage:
                      "linear-gradient(to left, black 45%, rgba(0,0,0,0.55) 72%, transparent 98%)",
                  }}
                />
              </>
            ) : (
              <img src={backdrop} alt="" className="h-full w-full object-cover" />
            )
          ) : (
            <div className="h-full w-full bg-[radial-gradient(800px_500px_at_60%_0%,rgb(143_29_44/0.35),transparent_60%)]" />
          )}
        </div>
        <div className="vignette" />
        <div className="absolute inset-0 bg-night-950/25" />
      </div>

      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="fixed right-5 top-5 z-20 flex h-11 w-11 items-center justify-center rounded-full bg-night-950/70 text-fog-300 ring-1 ring-night-500/60 backdrop-blur transition hover:rotate-90 hover:text-snow"
      >
        ✕
      </button>

      {/* Content rises over the parallax layer, vertically centered */}
      <div className="relative z-10 mx-auto flex min-h-full max-w-6xl flex-col justify-center px-5 py-24 sm:px-8">
        <div className="flex flex-col gap-10 md:flex-row md:items-center">
          {poster && (
            <div className="perspective-card hidden w-60 shrink-0 md:block lg:w-72">
              <div
                ref={tilt.ref}
                onPointerMove={tilt.onPointerMove}
                onPointerLeave={tilt.onPointerLeave}
                className="tilt-body relative overflow-hidden rounded-2xl shadow-card ring-1 ring-snow/15"
              >
                <img src={poster} alt={movie.title} className="block w-full" />
                <div className="tilt-glare" />
              </div>
            </div>
          )}

          <div className="min-w-0 flex-1">
            <p className="animate-rise text-[11px] font-medium uppercase tracking-[0.35em] text-gold-400">
              {[movie.year, movie.vote_count ? `${movie.vote_count.toLocaleString()} votes` : null]
                .filter(Boolean)
                .join("  ·  ")}
            </p>
            <h1
              className="animate-rise mt-2 font-display text-4xl font-bold leading-[0.98] tracking-tight text-snow drop-shadow-[0_4px_24px_rgba(0,0,0,0.9)] sm:text-6xl"
              style={{ animationDelay: "70ms" }}
            >
              {movie.title}
            </h1>
            {movie.tagline && (
              <p
                className="animate-rise mt-3 font-display text-base italic text-gold-300/90"
                style={{ animationDelay: "130ms" }}
              >
                “{movie.tagline}”
              </p>
            )}

            <div
              className="animate-rise mt-4 flex flex-wrap items-center gap-2 text-sm"
              style={{ animationDelay: "190ms" }}
            >
              {movie.vote_average ? (
                <span className="rounded-full bg-gold-500/15 px-2.5 py-0.5 font-semibold text-gold-400 ring-1 ring-gold-500/30">
                  ★ {movie.vote_average.toFixed(1)}
                </span>
              ) : null}
              {genres.slice(0, 5).map((genre) => (
                <span
                  key={genre}
                  className="rounded-full bg-snow/8 px-2.5 py-0.5 text-xs text-fog-300 ring-1 ring-snow/15"
                >
                  {genre}
                </span>
              ))}
              {moods.map((mood) => (
                <span
                  key={mood}
                  className="rounded-full bg-crimson-600/30 px-2 py-0.5 text-xs text-fog-300 ring-1 ring-crimson-500/30"
                >
                  {mood}
                </span>
              ))}
            </div>

            <div
              className="animate-rise mt-6 flex flex-wrap gap-2.5"
              style={{ animationDelay: "250ms" }}
            >
              <button
                type="button"
                onClick={() => void toggleFavorite(movie)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  favored
                    ? "bg-crimson-600/80 text-snow ring-1 ring-crimson-500"
                    : "bg-night-800/80 text-fog-300 ring-1 ring-night-500/60 backdrop-blur hover:text-snow"
                }`}
              >
                {favored ? "♥ Favorited" : "♡ Favorite"}
              </button>
              <button
                type="button"
                onClick={() => void toggleWatchlist(movie)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  listed
                    ? "bg-gold-500/20 text-gold-300 ring-1 ring-gold-500/50"
                    : "bg-night-800/80 text-fog-300 ring-1 ring-night-500/60 backdrop-blur hover:text-snow"
                }`}
              >
                {listed ? "✓ On watchlist" : "+ Watchlist"}
              </button>
              {listed && (
                <button
                  type="button"
                  onClick={() => void toggleWatched(listed.movie_key)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    listed.watched
                      ? "bg-gold-500 text-night-950"
                      : "bg-night-800/80 text-fog-300 ring-1 ring-night-500/60 backdrop-blur hover:text-snow"
                  }`}
                >
                  {listed.watched ? "✓ Watched" : "Mark watched"}
                </button>
              )}
              {tmdbHref && (
                <a
                  href={tmdbHref}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full bg-night-800/80 px-4 py-2 text-sm font-medium text-fog-300 ring-1 ring-night-500/60 backdrop-blur transition hover:text-snow"
                >
                  TMDB ↗
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Story + AI reasoning panel */}
        <div
          className="animate-rise mt-10 rounded-3xl bg-night-900/75 p-6 ring-1 ring-night-600/60 backdrop-blur-md sm:p-8 md:mr-24"
          style={{ animationDelay: "310ms" }}
        >
          {movie.match_reason && (
            <p className="mb-4 rounded-xl bg-night-700/70 px-3.5 py-2.5 text-xs italic text-gold-300/85 ring-1 ring-night-600/60">
              {movie.match_reason}
            </p>
          )}
          {explaining && (
            <div className="skeleton mb-4 h-10 rounded-xl" aria-label="Loading explanation" />
          )}
          {explanation && (
            <p className="mb-4 rounded-xl bg-gold-500/10 px-3.5 py-2.5 text-xs leading-relaxed text-gold-300 ring-1 ring-gold-500/25">
              {explanation}
            </p>
          )}
          {movie.overview && (
            <p className="text-sm leading-relaxed text-fog-300">{movie.overview}</p>
          )}
          {keywords.length > 0 && (
            <p className="mt-4 text-xs tracking-wide text-fog-500">{keywords.join(" · ")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
