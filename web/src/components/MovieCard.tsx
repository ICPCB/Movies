import { useState } from "react";
import { asList, posterUrl } from "../lib/tmdb";
import type { Movie } from "../lib/types";

interface MovieCardProps {
  movie: Movie;
  index?: number;
  onOpen: (movie: Movie) => void;
}

export default function MovieCard({ movie, index = 0, onOpen }: MovieCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const poster = posterUrl(movie.poster_path);
  const genres = asList(movie.genres).slice(0, 3);
  const moods = (movie.film_mood_tags ?? []).slice(0, 3);
  const rating = movie.vote_average ? movie.vote_average.toFixed(1) : null;

  return (
    <button
      type="button"
      onClick={() => onOpen(movie)}
      className="group animate-rise text-left"
      style={{ animationDelay: `${Math.min(index, 11) * 45}ms` }}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-2xl bg-night-700 shadow-card ring-1 ring-night-600/50 transition-all duration-300 group-hover:-translate-y-1.5 group-hover:shadow-glow">
        {poster && !imageFailed ? (
          <img
            src={poster}
            alt={movie.title}
            loading="lazy"
            onError={() => setImageFailed(true)}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.06]"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-night-600 via-night-700 to-night-800 p-4">
            <span className="font-display text-4xl font-bold text-gold-500/60">
              {movie.title.slice(0, 1)}
            </span>
            <span className="text-center font-display text-sm text-fog-400">
              {movie.title}
            </span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-night-950/95 via-night-950/15 to-transparent opacity-80 transition-opacity duration-300 group-hover:opacity-95" />
        {rating && (
          <span className="absolute right-2.5 top-2.5 rounded-full bg-night-950/80 px-2 py-0.5 text-xs font-semibold text-gold-400 ring-1 ring-gold-500/30 backdrop-blur">
            ★ {rating}
          </span>
        )}
        <div className="absolute inset-x-0 bottom-0 translate-y-1 p-3.5 transition-transform duration-300 group-hover:translate-y-0">
          <h3 className="font-display text-base font-semibold leading-snug text-snow">
            {movie.title}
            {movie.year ? (
              <span className="ml-1.5 text-sm font-normal text-fog-400">{movie.year}</span>
            ) : null}
          </h3>
          {genres.length > 0 && (
            <p className="mt-0.5 truncate text-xs text-fog-400">{genres.join(" · ")}</p>
          )}
          {moods.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {moods.map((mood) => (
                <span
                  key={mood}
                  className="rounded-full bg-crimson-600/35 px-1.5 py-px text-[10px] font-medium text-fog-300 ring-1 ring-crimson-500/30"
                >
                  {mood}
                </span>
              ))}
            </div>
          )}
          {movie.match_reason && (
            <p className="mt-1.5 line-clamp-2 text-[11px] italic leading-snug text-gold-300/80 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              {movie.match_reason}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
