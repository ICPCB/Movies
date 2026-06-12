const IMAGE_BASE = "https://image.tmdb.org/t/p";

export function posterUrl(posterPath: string | undefined, size: "w342" | "w500" | "w780" = "w342"): string | null {
  if (!posterPath) return null;
  const path = posterPath.startsWith("/") ? posterPath : `/${posterPath}`;
  return `${IMAGE_BASE}/${size}${path}`;
}

export function backdropUrl(backdropPath: string | undefined): string | null {
  if (!backdropPath) return null;
  const path = backdropPath.startsWith("/") ? backdropPath : `/${backdropPath}`;
  return `${IMAGE_BASE}/w780${path}`;
}

export function asList(value: string[] | string | undefined): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((item) => item.trim()).filter(Boolean);
  return value
    .split(/[|,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
