import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import CinematicHero from "../components/CinematicHero";
import ModeTabs, { type SearchTab } from "../components/ModeTabs";
import MoodChips from "../components/MoodChips";
import MovieDetail from "../components/MovieDetail";
import MovieGrid from "../components/MovieGrid";
import Pagination from "../components/Pagination";
import ReelOverlay from "../components/ReelOverlay";
import { moodsToIntentFields } from "../data/moods";
import { api, emptyIntent } from "../lib/api";
import type { CategoriesResponse, Intent, Movie } from "../lib/types";

const PAGE_SIZE = 18;

interface ResultsState {
  movies: Movie[];
  page: number;
  totalPool: number;
  cacheHit: boolean;
  cacheKey: string | null;
  headline: string;
}

export default function Home() {
  const location = useLocation();
  const [tab, setTab] = useState<SearchTab>("mood");
  const [text, setText] = useState("");
  const [selectedMoods, setSelectedMoods] = useState<string[]>([]);
  const [categories, setCategories] = useState<CategoriesResponse | null>(null);
  const [results, setResults] = useState<ResultsState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openMovie, setOpenMovie] = useState<Movie | null>(null);
  const [reel, setReel] = useState<{ pool: Movie[]; result: Movie | null } | null>(null);
  const activeIntent = useRef<Intent | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories(null));
  }, []);

  const runSearch = useCallback(async (intent: Intent, page: number, headline: string) => {
    activeIntent.current = intent;
    setLoading(true);
    setError(null);
    try {
      const response = await api.recommend({
        intent,
        page,
        page_size: PAGE_SIZE,
        log_history: page === 1,
      });
      setResults({
        movies: response.results,
        page: response.page,
        totalPool: response.total_pool,
        cacheHit: response.cache_hit,
        cacheKey: response.cache_key,
        headline,
      });
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  // A history "Run again" navigates here with a saved intent.
  useEffect(() => {
    const state = location.state as { rerunIntent?: Intent } | null;
    if (state?.rerunIntent) {
      const intent = state.rerunIntent;
      setTab(
        intent.mode === "mood" || intent.mode === "category" ? intent.mode : "content",
      );
      setText(intent.free_text_query);
      setSelectedMoods(intent.user_moods);
      void runSearch(intent, 1, intent.free_text_query || "from your history");
      window.history.replaceState({}, "");
    }
  }, [location.state, runSearch]);

  const submitMood = async () => {
    if (selectedMoods.length === 0 && !text.trim()) {
      setError("Pick at least one mood chip, or tell us how you feel.");
      return;
    }
    let intent: Intent;
    if (selectedMoods.length === 0) {
      // No chips: let the server's deterministic lexicon parser read the
      // feeling words (it knows the full vocabulary, incl. body sensations).
      try {
        const parsed = await api.parseIntent(text.trim(), "mood");
        intent = parsed.intent;
      } catch {
        intent = emptyIntent(text.trim(), "mood");
      }
    } else {
      intent = emptyIntent(text.trim(), "mood");
      Object.assign(intent, moodsToIntentFields(selectedMoods));
      intent.confidence = 1.0;
    }
    const label =
      selectedMoods.length > 0
        ? `feeling ${selectedMoods.length > 1 ? "a mix of things" : "something specific"}`
        : text.trim();
    void runSearch(intent, 1, `Films for tonight — ${label}`);
  };

  const submitContent = () => {
    if (!text.trim()) {
      setError("Describe the movie you're looking for first.");
      return;
    }
    const mode = selectedMoods.length > 0 ? "hybrid" : "content";
    const intent = emptyIntent(text.trim(), mode);
    if (mode === "hybrid") Object.assign(intent, moodsToIntentFields(selectedMoods));
    intent.confidence = 1.0;
    void runSearch(intent, 1, `“${text.trim()}”`);
  };

  const submitGenre = (genre: string) => {
    const intent = emptyIntent(`${genre} movies`, "category");
    intent.genres_include = [genre];
    intent.confidence = 1.0;
    void runSearch(intent, 1, `${genre} picks`);
  };

  const submitEra = (label: string, minYear: number | null, maxYear: number | null) => {
    const intent = emptyIntent(`great movies of the ${label}`, "category");
    intent.era = { min_year: minYear, max_year: maxYear };
    intent.confidence = 1.0;
    void runSearch(intent, 1, `${label} picks`);
  };

  const submitRandom = () => {
    setError(null);
    setReel({ pool: results?.movies ?? [], result: null });
    api
      .random()
      .then((movie) => setReel((current) => (current ? { ...current, result: movie } : current)))
      .catch((cause) => {
        setReel(null);
        setError(cause instanceof Error ? cause.message : String(cause));
      });
  };

  const landRandom = useCallback((movie: Movie) => {
    setReel(null);
    setResults({
      movies: [movie],
      page: 1,
      totalPool: 1,
      cacheHit: false,
      cacheKey: null,
      headline: "The reel has spoken",
    });
    setOpenMovie(movie);
  }, []);

  const goToPage = (page: number) => {
    const intent = activeIntent.current;
    if (intent && results) void runSearch(intent, page, results.headline);
  };

  const reroll = () => {
    const intent = activeIntent.current;
    if (!intent || !results) return;
    const totalPages = Math.max(1, Math.ceil(results.totalPool / PAGE_SIZE));
    void runSearch(intent, (results.page % totalPages) + 1, results.headline);
  };

  const toggleMood = (slug: string) =>
    setSelectedMoods((current) =>
      current.includes(slug)
        ? current.filter((value) => value !== slug)
        : [...current, slug],
    );

  const showTextInput = tab === "mood" || tab === "content";

  return (
    <>
      {/* Hero */}
      <CinematicHero onOpen={setOpenMovie}>
          <p className="animate-rise text-xs font-medium uppercase tracking-[0.3em] text-gold-500">
            local · private · real movies only
          </p>
          <h1
            className="animate-rise mt-4 font-display text-4xl font-bold leading-tight tracking-tight text-snow drop-shadow-[0_2px_16px_rgba(0,0,0,0.85)] sm:text-6xl"
            style={{ animationDelay: "60ms" }}
          >
            Find the film your
            <span className="text-gold-500"> evening deserves</span>
          </h1>
          <p
            className="animate-rise mx-auto mt-4 max-w-xl text-sm leading-relaxed text-fog-300 drop-shadow-[0_1px_8px_rgba(0,0,0,0.9)] sm:text-base"
            style={{ animationDelay: "120ms" }}
          >
            Tell CineMatch how you feel or what you want to watch. A local engine searches
            27,000+ real films — nothing invented, nothing leaves your machine.
          </p>

          <div className="animate-rise mt-8" style={{ animationDelay: "180ms" }}>
            <ModeTabs active={tab} onChange={setTab} />
          </div>

          {showTextInput && (
            <form
              className="animate-rise mx-auto mt-6 flex max-w-2xl items-center gap-2"
              style={{ animationDelay: "240ms" }}
              onSubmit={(event) => {
                event.preventDefault();
                tab === "mood" ? submitMood() : submitContent();
              }}
            >
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder={
                  tab === "mood"
                    ? "Optional — add your own words: drained after work, missing home…"
                    : "A slow-burn heist in winter… two strangers on a train…"
                }
                className="h-12 w-full rounded-full border border-night-500/60 bg-night-800/90 px-5 text-sm text-snow placeholder-fog-500 outline-none ring-gold-500/40 backdrop-blur transition focus:border-gold-500/50 focus:ring-2"
              />
              <button
                type="submit"
                disabled={loading}
                className="h-12 shrink-0 rounded-full bg-gold-500 px-6 font-display text-sm font-semibold text-night-950 shadow-glow transition hover:bg-gold-400 disabled:opacity-60"
              >
                {loading ? "Searching…" : "Search"}
              </button>
            </form>
          )}

          {tab === "mood" && (
            <div className="animate-rise mt-6" style={{ animationDelay: "300ms" }}>
              <MoodChips selected={selectedMoods} onToggle={toggleMood} />
              <p className="mt-3 text-xs text-fog-500">
                Chips describe how <em>you</em> feel — CineMatch picks films that answer the
                feeling, not mirror it.
              </p>
            </div>
          )}

          {tab === "content" && selectedMoods.length > 0 && (
            <p className="animate-rise mt-4 text-xs text-fog-500">
              {selectedMoods.length} mood chip{selectedMoods.length > 1 ? "s" : ""} still
              selected — this search runs in hybrid mode.
            </p>
          )}

          {tab === "category" && (
            <div className="animate-rise mt-8 space-y-6" style={{ animationDelay: "240ms" }}>
              <div>
                <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.25em] text-fog-500">
                  By genre
                </h2>
                <div className="flex flex-wrap justify-center gap-2">
                  {(categories?.genres ?? []).map((genre) => (
                    <button
                      key={genre}
                      type="button"
                      onClick={() => submitGenre(genre)}
                      className="rounded-full bg-night-700/80 px-3.5 py-1.5 text-sm text-fog-300 ring-1 ring-night-500/60 transition hover:-translate-y-0.5 hover:text-gold-300"
                    >
                      {genre}
                    </button>
                  ))}
                  {!categories && (
                    <span className="text-sm text-fog-500">Loading genres…</span>
                  )}
                </div>
              </div>
              <div>
                <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.25em] text-fog-500">
                  By era
                </h2>
                <div className="flex flex-wrap justify-center gap-2">
                  {(categories?.eras ?? []).map((era) => (
                    <button
                      key={era.label}
                      type="button"
                      onClick={() => submitEra(era.label, era.min_year, era.max_year)}
                      className="rounded-full bg-crimson-600/25 px-3.5 py-1.5 text-sm text-fog-300 ring-1 ring-crimson-500/30 transition hover:-translate-y-0.5 hover:text-snow"
                    >
                      {era.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "random" && (
            <div className="animate-rise mt-10" style={{ animationDelay: "240ms" }}>
              <button
                type="button"
                onClick={() => void submitRandom()}
                disabled={loading}
                className="group relative rounded-full bg-crimson-600 px-10 py-4 font-display text-lg font-semibold text-snow shadow-card ring-1 ring-crimson-500 transition hover:bg-crimson-500 disabled:opacity-60"
              >
                <span className="mr-2 inline-block transition-transform duration-500 group-hover:rotate-180">
                  ⟳
                </span>
                {loading ? "Spinning…" : "Spin the reel"}
              </button>
              <p className="mt-3 text-xs text-fog-500">
                One quality-floored pick: 200+ votes, rated 6.0 or higher.
              </p>
            </div>
          )}

          {error && (
            <p className="mt-5 rounded-xl bg-crimson-600/15 px-4 py-2.5 text-sm text-crimson-500 ring-1 ring-crimson-600/40">
              {error}
            </p>
          )}
      </CinematicHero>

      {/* Results */}
      <section ref={resultsRef} className="mx-auto max-w-7xl scroll-mt-20 px-4 sm:px-6">
        {(results || loading) && (
          <div className="mb-5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="font-display text-2xl font-semibold text-snow">
              {loading ? "Searching the archive…" : results?.headline}
            </h2>
            {!loading && results && results.totalPool > 1 && (
              <span className="text-sm text-fog-500">
                {results.totalPool} matches{results.cacheHit ? " · instant (cached)" : ""}
              </span>
            )}
          </div>
        )}
        {(results || loading) && (
          <MovieGrid
            movies={results?.movies ?? []}
            loading={loading}
            skeletonCount={PAGE_SIZE}
            onOpen={setOpenMovie}
          />
        )}
        {results && !loading && results.totalPool > PAGE_SIZE && (
          <Pagination
            page={results.page}
            totalPool={results.totalPool}
            pageSize={PAGE_SIZE}
            onPage={goToPage}
            onReroll={reroll}
          />
        )}
      </section>

      <MovieDetail
        movie={openMovie}
        cacheKey={results?.cacheKey}
        onClose={() => setOpenMovie(null)}
      />

      {reel && (
        <ReelOverlay
          pool={reel.pool}
          result={reel.result}
          onDone={landRandom}
          onCancel={() => setReel(null)}
        />
      )}
    </>
  );
}
