import MovieCard from "./MovieCard";
import SkeletonCard from "./SkeletonCard";
import type { Movie } from "../lib/types";

interface MovieGridProps {
  movies: Movie[];
  loading?: boolean;
  skeletonCount?: number;
  onOpen: (movie: Movie) => void;
}

export default function MovieGrid({
  movies,
  loading = false,
  skeletonCount = 12,
  onOpen,
}: MovieGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {loading
        ? Array.from({ length: skeletonCount }, (_, index) => <SkeletonCard key={index} />)
        : movies.map((movie, index) => (
            <MovieCard
              key={movie.movie_key ?? `${movie.title}-${movie.year}-${index}`}
              movie={movie}
              index={index}
              onOpen={onOpen}
            />
          ))}
    </div>
  );
}
