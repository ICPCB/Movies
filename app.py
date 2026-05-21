"""
CineMatch — Gradio UI (UI-only layer)
Delegates all retrieval to src/pipelines/{basic,advanced,hybrid}.py
"""
import html
import gradio as gr
from src import config as runtime_config
from src.config import DATASET_ROW_COUNT, TMDB_IMAGE_BASE
from src.pipelines import basic as basic_pipeline
from src.pipelines import advanced as advanced_pipeline
from src.pipelines import hybrid as hybrid_pipeline
from src.utils.dedup import deduplicate_movies


# ---------- HTML HELPERS ----------

def safe(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def get_year(release_date) -> str:
    s = str(release_date)
    return s[:4] if s and s != "nan" else "????"


def get_poster_url(poster_path) -> str:
    p = str(poster_path)
    if not p or p == "nan":
        return ""
    if p.startswith("http"):
        return p
    return TMDB_IMAGE_BASE + ("" if p.startswith("/") else "/") + p


# ---------- MOVIE CARD RENDERER ----------

def render_movie_cards(query: str, movies: list[dict], pipeline_name: str) -> str:
    cards = ""
    for idx, movie in enumerate(movies, 1):
        title = safe(movie.get("title", ""))
        genres = safe(movie.get("genres", ""))
        overview = safe(movie.get("overview", ""))
        year = safe(get_year(movie.get("release_date", "")))
        rating = float(movie.get("vote_average") or 0)

        # `final_score` is the score this pipeline actually ordered by
        # (semantic in Basic, rrf in Hybrid pre-rerank, rerank otherwise).
        # The "match" pill always reflects that, never a different
        # score type mixed in by accident.
        final_score = movie.get("final_score")
        if final_score is None:
            final_score = (
                movie.get("rerank_score")
                or movie.get("rrf_score")
                or movie.get("semantic_score")
                or 0.0
            )
        final_score = float(final_score)
        rerank_score = movie.get("rerank_score")
        poster_url = get_poster_url(movie.get("poster_path", ""))

        poster_html = (
            f'<img class="movie-poster" src="{poster_url}" alt="{title} poster">'
            if poster_url
            else '<div class="poster-placeholder">🎬</div>'
        )

        rerank_pill = (
            f'<span class="rerank-pill">🎯 {rerank_score:.2f}</span>'
            if rerank_score is not None else ""
        )

        explanation = movie.get("explanation", "")
        reason_html = ""
        if explanation:
            reason_html = f"""
            <div class="reason-box">
                <span class="reason-title">AI Match Reason</span>
                <p>{safe(explanation)}</p>
            </div>"""

        cards += f"""
        <article class="movie-card" style="animation-delay: {idx * 0.08}s">
            <div class="poster-wrap">
                <div class="rank-badge">#{idx}</div>
                {poster_html}
                <div class="poster-shine"></div>
            </div>
            <div class="movie-info">
                <div class="movie-topline">
                    <span class="year-pill">{year}</span>
                    <span class="score-pill">⭐ {rating:.1f}</span>
                    <span class="match-pill" title="final_score">{final_score:.3f} match</span>
                    {rerank_pill}
                </div>
                <h3>{title}</h3>
                <p class="genres">{genres}</p>
                <p class="overview">{overview}</p>
                {reason_html}
            </div>
        </article>"""

    return f"""
    <section class="results-header">
        <div>
            <p class="eyebrow">Search results · {pipeline_name}</p>
            <h2>Recommended for "{safe(query)}"</h2>
        </div>
        <div style="display:flex;gap:12px;align-items:center;">
            <div class="model-chip">BGE-M3</div>
            <div class="pipeline-badge" style="padding:8px 14px;border-radius:20px;
                background:rgba(34,211,238,0.12);border:1px solid rgba(34,211,238,0.25);
                font-size:12px;color:#67e8f9;font-weight:600;">✓ Pipeline Ready</div>
        </div>
    </section>
    <section class="movie-grid">{cards}</section>"""


# ---------- MAIN UI HANDLER ----------

def recommend_ui(query: str, top_k: int, use_llm: bool, pipeline_mode: str) -> str:
    if not query or not query.strip():
        return """
        <div class="empty-state">
            <div class="empty-icon">🔎</div>
            <h2>Tell me what movie you want</h2>
            <p>Example: "A dark sci-fi movie about dreams, memory, and reality."</p>
        </div>"""

    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        top_k = 6
    top_k = max(1, min(top_k, 20))

    try:
        runtime_config.LLM_RETRIEVAL_ENABLED = bool(use_llm)

        if pipeline_mode == "Basic (semantic only)":
            print(f"\n{'='*60}\n[BASIC] {query[:60]}")
            movies = basic_pipeline.run(query, top_k=top_k)
            label = "Basic Pipeline (BGE-M3 Semantic Only)"

        elif pipeline_mode == "Advanced (rerank + expand)":
            print(f"\n{'='*60}\n[ADVANCED] {query[:60]}")
            movies = advanced_pipeline.run(query, top_k=top_k, with_explanation=use_llm)
            label = "Advanced Pipeline (Expansion + Rerank)"

        elif pipeline_mode == "Hybrid (BM25 + semantic + rerank)":
            print(f"\n{'='*60}\n[HYBRID] {query[:60]}")
            movies = hybrid_pipeline.run(query, top_k=top_k, with_explanation=use_llm)
            label = "Hybrid Pipeline (BM25 + Semantic + Rerank)"

        else:
            movies = basic_pipeline.run(query, top_k=top_k)
            label = "Basic Pipeline"

        # Final safety net: never let a duplicate slip through to the UI.
        movies = deduplicate_movies(movies, prefer_score="final_score")[:top_k]
        print(f"  → {len(movies)} results | top: {movies[0].get('title') if movies else 'none'}")
        return render_movie_cards(query, movies, label)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"""
        <div class="empty-state">
            <div class="empty-icon">❌</div>
            <h2>Search Failed</h2>
            <p>{safe(str(e)[:200])}</p>
            <p style="color:#888;font-size:12px;">Check console for details</p>
        </div>"""


# ---------- CSS ----------

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg: #05060b;
    --bg-soft: #0b1020;
    --card: rgba(255, 255, 255, 0.075);
    --card-border: rgba(255, 255, 255, 0.14);
    --text: #f8fafc;
    --muted: #a8b3cf;
    --red: #ff2f5f;
    --orange: #ff9f43;
    --purple: #8b5cf6;
    --cyan: #22d3ee;
}

* { box-sizing: border-box; }

body, .gradio-container {
    background:
        radial-gradient(circle at 15% 10%, rgba(255, 47, 95, 0.28), transparent 32%),
        radial-gradient(circle at 90% 15%, rgba(139, 92, 246, 0.24), transparent 32%),
        radial-gradient(circle at 50% 100%, rgba(34, 211, 238, 0.14), transparent 40%),
        linear-gradient(135deg, #05060b 0%, #090d18 48%, #02030a 100%) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
}

.gradio-container { min-height: 100vh; }
footer { display: none !important; }
#main-shell { max-width: 1320px; margin: 0 auto; }

#hero {
    position: relative;
    overflow: hidden;
    padding: 34px;
    min-height: 430px;
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 34px;
    background:
        linear-gradient(90deg, rgba(5,6,11,0.96) 0%, rgba(5,6,11,0.72) 46%, rgba(5,6,11,0.25) 100%),
        url('https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1600&auto=format&fit=crop');
    background-size: cover;
    background-position: center;
    box-shadow: 0 30px 90px rgba(0, 0, 0, 0.48);
}

#hero::before {
    content: ""; position: absolute; inset: -120px;
    background: conic-gradient(from 90deg, transparent, rgba(255,47,95,0.22), transparent, rgba(34,211,238,0.18), transparent);
    animation: rotateGlow 12s linear infinite;
    opacity: 0.7;
}

#hero::after {
    content: ""; position: absolute; inset: 0;
    background:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: linear-gradient(to bottom, black, transparent);
    pointer-events: none;
}

.hero-content { position: relative; z-index: 2; max-width: 780px; animation: fadeUp 0.8s ease both; }
.navbar { position: relative; z-index: 3; display: flex; align-items: center; justify-content: space-between; margin-bottom: 70px; }
.logo { display: inline-flex; align-items: center; gap: 10px; font-weight: 900; letter-spacing: -0.04em; font-size: 22px; }
.logo-mark { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 14px; background: linear-gradient(135deg, var(--red), var(--orange)); box-shadow: 0 12px 30px rgba(255,47,95,0.35); }
.nav-pills { display: flex; gap: 10px; }
.nav-pills span { padding: 10px 16px; border-radius: 999px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); color: var(--muted); font-size: 14px; }
.eyebrow { margin: 0 0 14px 0; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.18em; font-size: 12px; font-weight: 800; }
.hero-content h1 { margin: 0; font-size: clamp(48px, 7vw, 92px); line-height: 0.92; letter-spacing: -0.075em; font-weight: 900; }
.gradient-text { background: linear-gradient(90deg, #fff, #ffd4df, #ff2f5f); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero-content p { margin-top: 24px; max-width: 620px; color: #cbd5e1; font-size: 18px; line-height: 1.75; }
.hero-stats { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 32px; }
.hero-stats div { padding: 14px 18px; border-radius: 20px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14); backdrop-filter: blur(18px); }
.hero-stats strong { display: block; font-size: 20px; }
.hero-stats span { color: var(--muted); font-size: 13px; }

.floating-card { position: absolute; right: 46px; bottom: 38px; z-index: 2; width: 255px; padding: 16px; border-radius: 28px; background: rgba(255,255,255,0.105); border: 1px solid rgba(255,255,255,0.16); backdrop-filter: blur(22px); box-shadow: 0 24px 70px rgba(0,0,0,0.4); animation: floatCard 4.5s ease-in-out infinite; }
.floating-card img { width: 100%; height: 300px; object-fit: cover; border-radius: 20px; }
.floating-card h3 { margin: 14px 0 4px; font-size: 18px; }
.floating-card p { margin: 0; color: var(--muted); font-size: 13px; }

#search-panel { margin-top: 24px; padding: 24px; border-radius: 30px; background: rgba(255,255,255,0.075); border: 1px solid rgba(255,255,255,0.14); backdrop-filter: blur(22px); box-shadow: 0 24px 80px rgba(0,0,0,0.36); animation: fadeUp 0.9s ease both; }
#search-panel label, #search-panel span { color: var(--text) !important; }
#search-panel textarea, #search-panel input, #search-panel select {
    background: rgba(3,7,18,0.72) !important;
    color: var(--text) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    border-radius: 18px !important;
}
#search-panel textarea::placeholder { color: rgba(203,213,225,0.55) !important; }

#search-btn { border: 0 !important; border-radius: 18px !important; min-height: 52px !important; color: white !important; font-weight: 900 !important; background: linear-gradient(135deg, var(--red), var(--orange)) !important; box-shadow: 0 16px 40px rgba(255,47,95,0.32) !important; transition: transform 0.22s ease, box-shadow 0.22s ease !important; }
#search-btn:hover { transform: translateY(-2px) scale(1.01); box-shadow: 0 22px 54px rgba(255,47,95,0.42) !important; }

#results { margin-top: 24px; }
.results-header { display: flex; justify-content: space-between; gap: 18px; align-items: center; margin: 30px 0 18px; }
.results-header h2 { margin: 0; font-size: clamp(26px, 4vw, 46px); letter-spacing: -0.055em; }
.model-chip { padding: 12px 16px; border-radius: 999px; color: #fff; background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.14); white-space: nowrap; }

.movie-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; }
.movie-card { position: relative; display: grid; grid-template-columns: 158px 1fr; gap: 18px; padding: 16px; min-height: 250px; border-radius: 28px; overflow: hidden; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.045)); border: 1px solid rgba(255,255,255,0.13); box-shadow: 0 22px 60px rgba(0,0,0,0.32); backdrop-filter: blur(24px); transform: translateY(18px); opacity: 0; animation: cardIn 0.68s ease forwards; transition: transform 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease; }
.movie-card:hover { transform: translateY(-8px) scale(1.01); border-color: rgba(255,47,95,0.45); box-shadow: 0 30px 90px rgba(255,47,95,0.18); }
.movie-card::before { content: ""; position: absolute; inset: 0; background: radial-gradient(circle at top left, rgba(255,47,95,0.18), transparent 35%); pointer-events: none; }

.poster-wrap { position: relative; overflow: hidden; border-radius: 22px; }
.movie-poster, .poster-placeholder { width: 100%; height: 235px; border-radius: 22px; object-fit: cover; background: linear-gradient(135deg, #1e293b, #0f172a); }
.poster-placeholder { display: grid; place-items: center; font-size: 44px; }

.rank-badge { position: absolute; top: 10px; left: 10px; z-index: 2; padding: 7px 10px; border-radius: 999px; font-weight: 900; font-size: 12px; color: white; background: rgba(0,0,0,0.55); border: 1px solid rgba(255,255,255,0.2); backdrop-filter: blur(12px); }
.poster-shine { position: absolute; inset: 0; transform: translateX(-140%); background: linear-gradient(90deg, transparent, rgba(255,255,255,0.22), transparent); transition: transform 0.7s ease; }
.movie-card:hover .poster-shine { transform: translateX(140%); }

.movie-info { position: relative; z-index: 2; }
.movie-topline { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.year-pill, .score-pill, .match-pill, .rerank-pill { padding: 7px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.12); }
.score-pill { background: rgba(255,159,67,0.15); }
.match-pill { background: rgba(34,211,238,0.12); }
.rerank-pill { background: rgba(139,92,246,0.18); border-color: rgba(139,92,246,0.3); }

.movie-info h3 { margin: 0; color: white; font-size: 24px; line-height: 1.1; letter-spacing: -0.04em; }
.genres { margin: 9px 0 10px; color: #ffb4c7; font-size: 14px; font-weight: 700; }
.overview { margin: 0; color: #cbd5e1; line-height: 1.62; font-size: 14px; }

.reason-box { margin-top: 14px; padding: 13px 14px; border-radius: 18px; background: rgba(34,211,238,0.08); border: 1px solid rgba(34,211,238,0.18); }
.reason-title { display: block; margin-bottom: 5px; color: #67e8f9; font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.11em; }
.reason-box p { margin: 0; color: #dbeafe; font-size: 13px; line-height: 1.55; }

.empty-state { margin-top: 28px; padding: 60px 24px; border-radius: 30px; text-align: center; background: rgba(255,255,255,0.065); border: 1px solid rgba(255,255,255,0.12); }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-state h2 { margin: 0; font-size: 34px; letter-spacing: -0.05em; }
.empty-state p { color: var(--muted); }

.gradio-container .examples { background: rgba(255,255,255,0.06) !important; border-radius: 22px !important; border: 1px solid rgba(255,255,255,0.11) !important; }

@keyframes fadeUp { from { transform: translateY(22px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes cardIn { to { transform: translateY(0); opacity: 1; } }
@keyframes floatCard { 0%, 100% { transform: translateY(0) rotate(1deg); } 50% { transform: translateY(-14px) rotate(-1deg); } }
@keyframes rotateGlow { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
    #hero { padding: 24px; }
    .navbar { align-items: flex-start; gap: 14px; flex-direction: column; margin-bottom: 42px; }
    .floating-card { display: none; }
    .movie-grid { grid-template-columns: 1fr; }
    .movie-card { grid-template-columns: 120px 1fr; }
    .movie-poster, .poster-placeholder { height: 185px; }
}
@media (max-width: 560px) {
    .movie-card { grid-template-columns: 1fr; }
    .movie-poster, .poster-placeholder { height: 340px; }
    .results-header { align-items: flex-start; flex-direction: column; }
}
"""

HERO_HTML = f"""
<div id="hero">
    <div class="navbar">
        <div class="logo">
            <span class="logo-mark">🎬</span>
            <span>CineMatch</span>
        </div>
        <div class="nav-pills">
            <span>Semantic Search</span>
            <span>AI Recommender</span>
            <span>Movie DB</span>
        </div>
    </div>
    <div class="hero-content">
        <p class="eyebrow">AI Movie Discovery</p>
        <h1>Movies Searching<br><span class="gradient-text">and Recommender</span></h1>
        <p>Describe the vibe, story, genre, character, or feeling you want.
           Choose between Basic, Advanced, or Hybrid search pipelines.</p>
        <div class="hero-stats">
            <div><strong>{DATASET_ROW_COUNT:,}</strong><span>Movies indexed</span></div>
            <div><strong>BGE-M3</strong><span>Semantic Embedding</span></div>
            <div><strong>Hybrid</strong><span>BM25 + Rerank</span></div>
        </div>
    </div>
    <div class="floating-card">
        <img src="https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=800&auto=format&fit=crop" alt="movie posters">
        <h3>Find your next movie</h3>
        <p>Search by meaning, mood, or story.</p>
    </div>
</div>
"""

APP_THEME = gr.themes.Base(
    primary_hue="red",
    secondary_hue="orange",
    neutral_hue="slate",
)

# ---------- BUILD UI ----------

with gr.Blocks(
    title="CineMatch — Movie Recommender",
) as app:

    with gr.Column(elem_id="main-shell"):
        gr.HTML(HERO_HTML)

        with gr.Group(elem_id="search-panel"):
            query = gr.Textbox(
                label="What kind of movie do you want?",
                placeholder='Example: "A dark sci-fi movie about dreams, memory, and reality."',
                info="CineMatch is optimized for English TMDB metadata. Please enter your movie request in English.",
                lines=3,
            )
            pipeline_mode = gr.Dropdown(
                choices=[
                    "Basic (semantic only)",
                    "Advanced (rerank + expand)",
                    "Hybrid (BM25 + semantic + rerank)",
                ],
                value="Hybrid (BM25 + semantic + rerank)",
                label="Search Pipeline",
                info="Basic = fastest | Advanced = accurate | Hybrid = most accurate",
            )
            with gr.Row():
                top_k = gr.Slider(minimum=1, maximum=20, value=6, step=1, label="Number of movies")
                use_llm = gr.Checkbox(value=True, label="AI expansion and explanation (LLM)")
            submit = gr.Button("Search Movies", variant="primary", elem_id="search-btn")

        output = gr.HTML(elem_id="results")

        gr.Examples(
            examples=[
                ["Movie about robots fighting monsters in the sea"],
                ["A heartwarming animated film about friendship"],
                ["Psychological thriller with a shocking twist"],
                ["Slow beautiful film about loneliness in a big city"],
                ["Christopher Nolan thriller"],
                ["Highly rated sci-fi film after 2015"],
            ],
            inputs=query,
        )

    submit.click(
        recommend_ui,
        inputs=[query, top_k, use_llm, pipeline_mode],
        outputs=output,
    )

if __name__ == "__main__":
    app.queue()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=True,
        css=CUSTOM_CSS,
        theme=APP_THEME,
    )
