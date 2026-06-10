import { useState } from "react";
import { useLibrary } from "../hooks/useLibrary";
import { posterUrl } from "../lib/tmdb";
import type { FavoriteItem, WatchlistItem } from "../lib/types";

type WatchFilter = "all" | "unwatched" | "watched";

function PosterThumb({ item }: { item: FavoriteItem | WatchlistItem }) {
  const poster = posterUrl(item.poster_path);
  return poster ? (
    <img
      src={poster}
      alt={item.title}
      loading="lazy"
      className="h-full w-full object-cover"
    />
  ) : (
    <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-night-600 to-night-800">
      <span className="font-display text-2xl font-bold text-gold-500/50">
        {item.title.slice(0, 1)}
      </span>
    </div>
  );
}

export default function Library() {
  const { favorites, watchlist, toggleWatched, removeWatchlist, toggleFavorite } =
    useLibrary();
  const [filter, setFilter] = useState<WatchFilter>("all");

  const filteredWatchlist = watchlist.filter((item) =>
    filter === "all" ? true : filter === "watched" ? item.watched : !item.watched,
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
      <h1 className="animate-rise font-display text-3xl font-bold tracking-tight text-snow">
        Your library
      </h1>

      {/* Favorites */}
      <section className="mt-8">
        <h2 className="mb-4 font-display text-xl font-semibold text-gold-400">
          ♥ Favorites
          <span className="ml-2 text-sm font-normal text-fog-500">{favorites.length}</span>
        </h2>
        {favorites.length === 0 ? (
          <p className="rounded-2xl bg-night-800/70 px-5 py-8 text-center text-sm text-fog-500 ring-1 ring-night-600/50">
            Nothing favorited yet — open any movie and tap ♡.
          </p>
        ) : (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8">
            {favorites.map((item, index) => (
              <div
                key={item.movie_key}
                className="group animate-rise"
                style={{ animationDelay: `${Math.min(index, 11) * 40}ms` }}
              >
                <div className="relative aspect-[2/3] overflow-hidden rounded-xl ring-1 ring-night-600/50 transition group-hover:shadow-glow">
                  <PosterThumb item={item} />
                  <button
                    type="button"
                    title="Remove from favorites"
                    onClick={() =>
                      void toggleFavorite({ movie_key: item.movie_key, title: item.title })
                    }
                    className="absolute right-1.5 top-1.5 hidden h-7 w-7 items-center justify-center rounded-full bg-night-950/80 text-xs text-fog-300 backdrop-blur transition hover:text-crimson-500 group-hover:flex"
                  >
                    ✕
                  </button>
                </div>
                <p className="mt-1.5 truncate text-xs text-fog-300">{item.title}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Watchlist */}
      <section className="mt-12">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <h2 className="font-display text-xl font-semibold text-gold-400">
            + Watchlist
            <span className="ml-2 text-sm font-normal text-fog-500">{watchlist.length}</span>
          </h2>
          <div className="inline-flex rounded-full bg-night-800/80 p-1 ring-1 ring-night-500/50">
            {(["all", "unwatched", "watched"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
                  filter === value
                    ? "bg-gold-500 text-night-950"
                    : "text-fog-400 hover:text-snow"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        {filteredWatchlist.length === 0 ? (
          <p className="rounded-2xl bg-night-800/70 px-5 py-8 text-center text-sm text-fog-500 ring-1 ring-night-600/50">
            {watchlist.length === 0
              ? "Your watchlist is empty — open any movie and tap + Watchlist."
              : "No titles match this filter."}
          </p>
        ) : (
          <ul className="space-y-2.5">
            {filteredWatchlist.map((item, index) => (
              <li
                key={item.movie_key}
                className="animate-rise flex items-center gap-4 rounded-2xl bg-night-800/70 p-3 ring-1 ring-night-600/50 transition hover:ring-night-500"
                style={{ animationDelay: `${Math.min(index, 11) * 40}ms` }}
              >
                <div className="h-16 w-11 shrink-0 overflow-hidden rounded-lg">
                  <PosterThumb item={item} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className={`truncate font-medium ${item.watched ? "text-fog-500 line-through" : "text-snow"}`}>
                    {item.title}
                  </p>
                  <p className="text-xs text-fog-500">
                    {item.watched && item.watched_at
                      ? `watched ${new Date(item.watched_at).toLocaleDateString()}`
                      : `added ${new Date(item.added_at).toLocaleDateString()}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void toggleWatched(item.movie_key)}
                  className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                    item.watched
                      ? "bg-gold-500 text-night-950"
                      : "bg-night-700 text-fog-300 ring-1 ring-night-500/60 hover:text-snow"
                  }`}
                >
                  {item.watched ? "✓ Watched" : "Mark watched"}
                </button>
                <button
                  type="button"
                  title="Remove from watchlist"
                  onClick={() => void removeWatchlist(item.movie_key)}
                  className="shrink-0 rounded-full px-2 py-1.5 text-xs text-fog-500 transition hover:text-crimson-500"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
