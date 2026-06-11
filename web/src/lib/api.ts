import type {
  CategoriesResponse,
  FavoriteItem,
  HistoryItem,
  Intent,
  Mode,
  Movie,
  RecommendResponse,
  WatchlistItem,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText}${body ? ` — ${body}` : ""}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function emptyIntent(freeText: string, mode: Mode = "content"): Intent {
  return {
    mode,
    user_moods: [],
    desired_film_moods: [],
    avoid_film_moods: [],
    plot_elements: [],
    genres_include: [],
    genres_exclude: [],
    era: { min_year: null, max_year: null },
    tone: { darkness: 0.0, intensity: 0.0 },
    constraints: { min_rating: null },
    free_text_query: freeText,
    confidence: 0.0,
  };
}

export const api = {
  recommend: (body: {
    intent?: Intent;
    free_text?: string;
    mode?: Mode;
    page?: number;
    page_size?: number;
    log_history?: boolean;
  }) =>
    request<RecommendResponse>("/api/recommend", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  parseIntent: (text: string, mode: Mode = "content") =>
    request<{ intent: Intent; query: unknown }>("/api/parse-intent", {
      method: "POST",
      body: JSON.stringify({ text, mode }),
    }),

  explain: (cacheKey: string, movieKey: string) =>
    request<{ movie_key: string; explanation: string }>(
      `/api/explain/${encodeURIComponent(cacheKey)}/${encodeURIComponent(movieKey)}`,
    ),

  categories: () => request<CategoriesResponse>("/api/categories"),

  random: () => request<Movie>("/api/random"),

  movie: (tmdbId: number) => request<Movie>(`/api/movies/${tmdbId}`),

  favorites: {
    list: () => request<FavoriteItem[]>("/api/favorites"),
    add: (movie: { movie_key: string; tmdb_id?: number | null; title: string; poster_path?: string }) =>
      request<FavoriteItem>("/api/favorites", {
        method: "POST",
        body: JSON.stringify({ poster_path: "", tmdb_id: null, ...movie }),
      }),
    remove: (movieKey: string) =>
      request<void>(`/api/favorites/${encodeURIComponent(movieKey)}`, { method: "DELETE" }),
  },

  watchlist: {
    list: () => request<WatchlistItem[]>("/api/watchlist"),
    add: (movie: { movie_key: string; tmdb_id?: number | null; title: string; poster_path?: string }) =>
      request<WatchlistItem>("/api/watchlist", {
        method: "POST",
        body: JSON.stringify({ poster_path: "", tmdb_id: null, ...movie }),
      }),
    setWatched: (movieKey: string, watched: boolean) =>
      request<WatchlistItem>(`/api/watchlist/${encodeURIComponent(movieKey)}`, {
        method: "PATCH",
        body: JSON.stringify({ watched }),
      }),
    remove: (movieKey: string) =>
      request<void>(`/api/watchlist/${encodeURIComponent(movieKey)}`, { method: "DELETE" }),
  },

  history: {
    list: () => request<HistoryItem[]>("/api/history"),
    clear: () => request<void>("/api/history", { method: "DELETE" }),
  },
};
