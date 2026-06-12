import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { asList, backdropUrl, posterUrl } from "../lib/tmdb";
import type { Movie } from "../lib/types";

const ROTATE_MS = 8000;
const SLOTS = 5;

interface CinematicHeroProps {
  onOpen: (movie: Movie) => void;
  children: React.ReactNode;
}

/**
 * Full-bleed rotating hero. Pulls a handful of quality-floored random picks,
 * crossfades between their backdrops with a slow Ken Burns push-in, and
 * floats the search panel over the lower third.
 */
export default function CinematicHero({ onOpen, children }: CinematicHeroProps) {
  const [featured, setFeatured] = useState<Movie[]>([]);
  const [active, setActive] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled(Array.from({ length: SLOTS }, () => api.random()))
      .then((settled) => {
        if (cancelled) return;
        const seen = new Set<string>();
        const movies: Movie[] = [];
        for (const result of settled) {
          if (result.status !== "fulfilled") continue;
          const movie = result.value;
          const key = movie.movie_key ?? movie.title;
          // The local dataset rarely carries backdrops — posters work too
          // (blurred to ambient fill, sharp copy shown in the credit block).
          if (seen.has(key) || (!backdropUrl(movie.backdrop_path) && !posterUrl(movie.poster_path))) {
            continue;
          }
          seen.add(key);
          movies.push(movie);
        }
        setFeatured(movies);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Rotation pauses while the pointer hovers the credit block so the
  // featured film cannot swap out from under a click.
  useEffect(() => {
    if (featured.length < 2 || paused) return;
    timer.current = setInterval(
      () => setActive((index) => (index + 1) % featured.length),
      ROTATE_MS,
    );
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [featured.length, paused]);

  const movie = featured[active];
  const genres = movie ? asList(movie.genres).slice(0, 3) : [];

  return (
    <section className="relative overflow-hidden">
      {/* Backdrop stack: every slide stays mounted, opacity crossfades */}
      <div className="absolute inset-0">
        {featured.map((slide, index) => {
          const wide = backdropUrl(slide.backdrop_path);
          const tall = posterUrl(slide.poster_path, "w500");
          const url = wide ?? tall;
          const blurred = !wide; // posters become an ambient, blurred fill
          return (
            <div
              key={slide.movie_key ?? slide.title}
              className="absolute inset-0 transition-opacity duration-[1400ms] ease-out"
              style={{ opacity: index === active ? 1 : 0 }}
              aria-hidden={index !== active}
            >
              {url && (
                <img
                  src={url}
                  alt=""
                  className={`h-full w-full object-cover ${blurred ? "scale-110 blur-2xl saturate-125 opacity-80" : ""} ${
                    index === active ? "animate-kenburns" : ""
                  }`}
                />
              )}
            </div>
          );
        })}
        {/* Fallback atmosphere when no featured backdrop is available */}
        {featured.length === 0 && (
          <div className="absolute inset-0 bg-[radial-gradient(900px_400px_at_50%_-80px,rgb(143_29_44/0.25),transparent_65%)]" />
        )}
        <div className="vignette" />
      </div>

      {/* Featured movie credit, bottom-left like a one-sheet.
          The whole block is one big click target and pauses rotation on hover
          so the film can't swap out from under the cursor. */}
      {movie && (
        <div
          key={movie.movie_key ?? movie.title}
          role="button"
          tabIndex={0}
          onClick={() => onOpen(movie)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") onOpen(movie);
          }}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          className="group/credit absolute bottom-6 left-4 z-10 hidden max-w-md cursor-pointer items-end gap-4 rounded-2xl p-2 transition hover:bg-night-950/40 hover:ring-1 hover:ring-snow/15 hover:backdrop-blur-sm sm:left-8 md:flex"
        >
          {posterUrl(movie.poster_path) && (
            <img
              src={posterUrl(movie.poster_path)!}
              alt=""
              className="animate-rise w-24 shrink-0 rounded-xl shadow-card ring-1 ring-snow/20 transition-transform duration-300 group-hover/credit:scale-105"
            />
          )}
          <div>
          <p className="animate-rise text-[10px] font-medium uppercase tracking-[0.35em] text-gold-400/90">
            now showing
          </p>
          <h2
            className="animate-rise mt-1 font-display text-3xl font-bold leading-none tracking-tight text-snow drop-shadow-[0_2px_12px_rgba(0,0,0,0.8)]"
            style={{ animationDelay: "80ms" }}
          >
            {movie.title}
          </h2>
          <p
            className="animate-rise mt-1.5 text-xs text-fog-300"
            style={{ animationDelay: "140ms" }}
          >
            {[movie.year, genres.join(" · "), movie.vote_average ? `★ ${movie.vote_average.toFixed(1)}` : null]
              .filter(Boolean)
              .join("  ·  ")}
          </p>
          <span
            className="animate-rise mt-3 inline-block rounded-full bg-snow/10 px-4 py-1.5 text-xs font-medium text-snow ring-1 ring-snow/25 backdrop-blur transition group-hover/credit:bg-gold-500 group-hover/credit:text-night-950"
            style={{ animationDelay: "200ms" }}
          >
            View details →
          </span>
          </div>
        </div>
      )}

      {/* Rotation progress dots */}
      {featured.length > 1 && (
        <div className="absolute bottom-6 right-4 z-10 flex gap-1.5 sm:right-8">
          {featured.map((slide, index) => (
            <button
              key={slide.movie_key ?? slide.title}
              type="button"
              aria-label={`Featured film ${index + 1}`}
              onClick={() => setActive(index)}
              className={`h-1 rounded-full transition-all duration-500 ${
                index === active ? "w-7 bg-gold-500" : "w-3 bg-snow/30 hover:bg-snow/60"
              }`}
            />
          ))}
        </div>
      )}

      {/* Search panel floats over the imagery */}
      <div className="relative z-10 mx-auto max-w-4xl px-4 pb-24 pt-16 text-center sm:px-6 sm:pt-24 md:pb-32">
        {children}
      </div>
    </section>
  );
}
