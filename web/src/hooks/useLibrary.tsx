import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../lib/api";
import type { FavoriteItem, Movie, WatchlistItem } from "../lib/types";

interface LibraryState {
  favorites: FavoriteItem[];
  watchlist: WatchlistItem[];
  isFavorite: (movieKey: string | undefined) => boolean;
  watchlistItem: (movieKey: string | undefined) => WatchlistItem | undefined;
  toggleFavorite: (movie: Movie) => Promise<void>;
  toggleWatchlist: (movie: Movie) => Promise<void>;
  toggleWatched: (movieKey: string) => Promise<void>;
  removeWatchlist: (movieKey: string) => Promise<void>;
  refresh: () => Promise<void>;
}

const LibraryContext = createContext<LibraryState | null>(null);

function libraryPayload(movie: Movie) {
  return {
    movie_key: movie.movie_key ?? `title:${movie.title.toLowerCase()}|year:${movie.year ?? ""}`,
    tmdb_id: movie.tmdb_id ?? null,
    title: movie.title,
    poster_path: movie.poster_path ?? "",
  };
}

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);

  const refresh = useCallback(async () => {
    const [favs, watch] = await Promise.all([
      api.favorites.list().catch(() => [] as FavoriteItem[]),
      api.watchlist.list().catch(() => [] as WatchlistItem[]),
    ]);
    setFavorites(favs);
    setWatchlist(watch);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const isFavorite = useCallback(
    (movieKey: string | undefined) =>
      Boolean(movieKey && favorites.some((item) => item.movie_key === movieKey)),
    [favorites],
  );

  const watchlistItem = useCallback(
    (movieKey: string | undefined) =>
      movieKey ? watchlist.find((item) => item.movie_key === movieKey) : undefined,
    [watchlist],
  );

  const toggleFavorite = useCallback(
    async (movie: Movie) => {
      const payload = libraryPayload(movie);
      if (favorites.some((item) => item.movie_key === payload.movie_key)) {
        await api.favorites.remove(payload.movie_key);
      } else {
        await api.favorites.add(payload);
      }
      await refresh();
    },
    [favorites, refresh],
  );

  const toggleWatchlist = useCallback(
    async (movie: Movie) => {
      const payload = libraryPayload(movie);
      if (watchlist.some((item) => item.movie_key === payload.movie_key)) {
        await api.watchlist.remove(payload.movie_key);
      } else {
        await api.watchlist.add(payload);
      }
      await refresh();
    },
    [watchlist, refresh],
  );

  const toggleWatched = useCallback(
    async (movieKey: string) => {
      const item = watchlist.find((entry) => entry.movie_key === movieKey);
      if (!item) return;
      await api.watchlist.setWatched(movieKey, !item.watched);
      await refresh();
    },
    [watchlist, refresh],
  );

  const removeWatchlist = useCallback(
    async (movieKey: string) => {
      await api.watchlist.remove(movieKey);
      await refresh();
    },
    [refresh],
  );

  const value = useMemo(
    () => ({
      favorites,
      watchlist,
      isFavorite,
      watchlistItem,
      toggleFavorite,
      toggleWatchlist,
      toggleWatched,
      removeWatchlist,
      refresh,
    }),
    [
      favorites,
      watchlist,
      isFavorite,
      watchlistItem,
      toggleFavorite,
      toggleWatchlist,
      toggleWatched,
      removeWatchlist,
      refresh,
    ],
  );

  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}

export function useLibrary(): LibraryState {
  const context = useContext(LibraryContext);
  if (!context) throw new Error("useLibrary must be used inside LibraryProvider");
  return context;
}
