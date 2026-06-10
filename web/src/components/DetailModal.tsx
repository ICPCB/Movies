import { useEffect } from "react";
import { useLibrary } from "../hooks/useLibrary";
import { asList, backdropUrl, posterUrl } from "../lib/tmdb";
import type { Movie } from "../lib/types";

interface DetailModalProps {
  movie: Movie | null;
  onClose: () => void;
}

export default function DetailModal({ movie, onClose }: DetailModalProps) {
  const { isFavorite, watchlistItem, toggleFavorite, toggleWatchlist, toggleWatched } =
    useLibrary();

  useEffect(() => {
    if (!movie) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [movie, onClose]);

  if (!movie) return null;

  const backdrop = backdropUrl(movie.backdrop_path) ?? posterUrl(movie.poster_path, "w500");
  const poster = posterUrl(movie.poster_path);
  const genres = asList(movie.genres);
  const keywords = asList(movie.keywords).slice(0, 8);
  const moods = movie.film_mood_tags ?? [];
  const favored = isFavorite(movie.movie_key);
  const listed = watchlistItem(movie.movie_key);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-night-950/80 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={movie.title}
    >
      <div
        className="animate-rise relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-night-800 shadow-card ring-1 ring-night-500/50 scrollbar-none"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="relative h-56 overflow-hidden rounded-t-3xl sm:h-72">
          {backdrop ? (
            <img src={backdrop} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="h-full w-full bg-gradient-to-br from-crimson-600/40 via-night-700 to-night-800" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-night-800 via-night-800/40 to-transparent" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-night-950/70 text-fog-300 ring-1 ring-night-500/60 backdrop-blur transition hover:text-snow"
          >
            ✕
          </button>
        </div>

        <div className="relative -mt-16 flex flex-col gap-5 p-6 sm:flex-row sm:p-8">
          {poster && (
            <img
              src={poster}
              alt={movie.title}
              className="hidden w-36 shrink-0 self-start rounded-2xl shadow-card ring-1 ring-night-500/60 sm:block"
            />
          )}
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-3xl font-bold tracking-tight text-snow">
              {movie.title}
            </h2>
            <p className="mt-1 text-sm text-fog-400">
              {[movie.year, genres.slice(0, 4).join(" · ")].filter(Boolean).join("  ·  ")}
            </p>
            {movie.tagline && (
              <p className="mt-2 font-display text-sm italic text-gold-300/90">
                “{movie.tagline}”
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              {movie.vote_average ? (
                <span className="rounded-full bg-gold-500/15 px-2.5 py-0.5 font-semibold text-gold-400 ring-1 ring-gold-500/30">
                  ★ {movie.vote_average.toFixed(1)}
                </span>
              ) : null}
              {movie.vote_count ? (
                <span className="text-xs text-fog-500">{movie.vote_count.toLocaleString()} votes</span>
              ) : null}
              {moods.map((mood) => (
                <span
                  key={mood}
                  className="rounded-full bg-crimson-600/30 px-2 py-0.5 text-xs text-fog-300 ring-1 ring-crimson-500/30"
                >
                  {mood}
                </span>
              ))}
            </div>
            {movie.match_reason && (
              <p className="mt-3 rounded-xl bg-night-700/70 px-3 py-2 text-xs italic text-gold-300/85 ring-1 ring-night-600/60">
                {movie.match_reason}
              </p>
            )}
            {movie.overview && (
              <p className="mt-4 text-sm leading-relaxed text-fog-300">{movie.overview}</p>
            )}
            {keywords.length > 0 && (
              <p className="mt-3 text-xs text-fog-500">{keywords.join(" · ")}</p>
            )}

            <div className="mt-6 flex flex-wrap gap-2.5">
              <button
                type="button"
                onClick={() => void toggleFavorite(movie)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  favored
                    ? "bg-crimson-600/80 text-snow ring-1 ring-crimson-500"
                    : "bg-night-700 text-fog-300 ring-1 ring-night-500/60 hover:text-snow"
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
                    : "bg-night-700 text-fog-300 ring-1 ring-night-500/60 hover:text-snow"
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
                      : "bg-night-700 text-fog-300 ring-1 ring-night-500/60 hover:text-snow"
                  }`}
                >
                  {listed.watched ? "✓ Watched" : "Mark watched"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
