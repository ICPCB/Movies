export type Mode = "mood" | "content" | "hybrid" | "category" | "random";

export interface Era {
  min_year: number | null;
  max_year: number | null;
}

export interface Intent {
  mode: Mode;
  user_moods: string[];
  desired_film_moods: string[];
  avoid_film_moods: string[];
  plot_elements: string[];
  genres_include: string[];
  genres_exclude: string[];
  era: Era;
  tone: { darkness: number; intensity: number };
  constraints: { min_rating: number | null };
  free_text_query: string;
  confidence: number;
}

export interface Movie {
  movie_key?: string;
  tmdb_id?: number;
  title: string;
  year?: number;
  genres?: string[] | string;
  overview?: string;
  keywords?: string[] | string;
  tagline?: string;
  vote_average?: number;
  vote_count?: number;
  popularity?: number;
  poster_path?: string;
  backdrop_path?: string;
  film_mood_tags?: string[];
  match_reason?: string;
  [extra: string]: unknown;
}

export interface RecommendResponse {
  results: Movie[];
  page: number;
  total_pool: number;
  cache_hit: boolean;
  cache_key: string;
}

export interface EraBucket {
  label: string;
  min_year: number | null;
  max_year: number | null;
}

export interface CategoriesResponse {
  genres: string[];
  eras: EraBucket[];
}

export interface FavoriteItem {
  id: number;
  movie_key: string;
  tmdb_id: number | null;
  title: string;
  poster_path: string;
  added_at: string;
}

export interface WatchlistItem extends FavoriteItem {
  watched: boolean;
  watched_at: string | null;
}

export interface HistoryItem {
  id: number;
  mode: Mode;
  query_text: string;
  intent_json: string;
  created_at: string;
}
