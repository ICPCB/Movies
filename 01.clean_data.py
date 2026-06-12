import pandas as pd

# ---------- CONFIG ----------
# Raw dataset download:
# https://www.kaggle.com/datasets/asaniczka/tmdb-movies-dataset-2023-930k-movies
INPUT_FILE = "data/TMDB_movie_dataset_v11.csv"
OUTPUT_FILE = "data/movies_clean.csv"

KEEP_COLUMNS = [
    "id",
    "title",
    "vote_average",
    "vote_count",
    "status",
    "release_date",
    "runtime",
    "adult",
    "homepage",
    "original_language",
    "original_title",
    "overview",
    "popularity",
    "poster_path",
    "tagline",
    "genres",
    "production_companies",
    "spoken_languages",
    "keywords",
]

MIN_OVERVIEW_LENGTH = 50
MIN_VOTE_COUNT = 50

# English-query scope does not require English-original-language films.
# TMDB provides English metadata for many global movies; keeping those
# rows improves recommendations for films like Parasite while preserving
# an English UI/query experience.
ENGLISH_ONLY = False


# ---------- HELPERS ----------
def safe_text(value):
    """Convert missing / bad text values into clean empty strings."""
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {"nan", "none", "null", "na"}:
        return ""

    return text


def clean_list_field(value):
    """
    Normalize TMDB comma-style fields such as:
    "Action, Adventure, Science Fiction"
    """
    text = safe_text(value)

    if not text:
        return ""

    items = [item.strip() for item in text.split(",") if item.strip()]
    return ", ".join(dict.fromkeys(items))


def clean_bool_adult(value):
    """Handle adult column whether it is boolean or string."""
    if isinstance(value, bool):
        return value

    text = safe_text(value).lower()
    return text in {"true", "1", "yes"}


def build_document(row):
    """
    Rich document for dense embedding.
    Keep it natural and non-repetitive.
    Do not stuff fields too much, because dense embeddings can get diluted.
    """
    parts = []

    title = safe_text(row.get("title", ""))
    original_title = safe_text(row.get("original_title", ""))

    parts.append(f"Title: {title}")

    if original_title and original_title != title:
        parts.append(f"Original title: {original_title}")

    if pd.notna(row.get("year")):
        parts.append(f"Year: {int(row['year'])} ({row['decade']})")

    genres = safe_text(row.get("genres_clean", ""))
    if genres:
        parts.append(f"Genres: {genres}")

    tagline = safe_text(row.get("tagline", ""))
    if tagline:
        parts.append(f"Tagline: {tagline}")

    overview = safe_text(row.get("overview", ""))
    if overview:
        parts.append(f"Plot: {overview}")

    keywords = safe_text(row.get("keywords_clean", ""))
    if keywords:
        parts.append(f"Themes and topics: {keywords}")

    return "\n".join(parts)


# ---------- LOAD ----------
print("Loading dataset...")
df = pd.read_csv(INPUT_FILE, low_memory=False)
print(f"  Loaded {len(df):,} movies")


# ---------- VALIDATE COLUMNS ----------
missing_columns = [col for col in KEEP_COLUMNS if col not in df.columns]
if missing_columns:
    raise ValueError(f"Missing required columns in input CSV: {missing_columns}")


# ---------- KEEP COLUMNS ----------
df = df[KEEP_COLUMNS].copy()


# ---------- BASIC TEXT CLEANING ----------
text_columns = [
    "title",
    "status",
    "release_date",
    "homepage",
    "original_language",
    "original_title",
    "overview",
    "poster_path",
    "tagline",
    "genres",
    "production_companies",
    "spoken_languages",
    "keywords",
]

for col in text_columns:
    df[col] = df[col].apply(safe_text)


# ---------- TYPE CLEANING ----------
df["id"] = pd.to_numeric(df["id"], errors="coerce")
df["vote_average"] = pd.to_numeric(df["vote_average"], errors="coerce").fillna(0.0)
df["vote_count"] = pd.to_numeric(df["vote_count"], errors="coerce").fillna(0).astype(int)
df["runtime"] = pd.to_numeric(df["runtime"], errors="coerce")
df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce").fillna(0.0)
df["adult"] = df["adult"].apply(clean_bool_adult)


# ---------- FILTER ----------
print("Cleaning...")

df = df.dropna(subset=["id"])
df["id"] = df["id"].astype(int)

df = df[df["title"] != ""]
df = df[df["overview"] != ""]
df = df[df["overview"].str.len() >= MIN_OVERVIEW_LENGTH]

df = df[df["status"].str.lower() == "released"]
df = df[df["adult"] == False]
df = df[df["vote_count"] >= MIN_VOTE_COUNT]

if ENGLISH_ONLY:
    df = df[df["original_language"].str.lower() == "en"]

print(f"  Kept {len(df):,} movies after filtering")


# ---------- CLEAN LIST-LIKE FIELDS ----------
df["genres_clean"] = df["genres"].apply(clean_list_field)
df["keywords_clean"] = df["keywords"].apply(clean_list_field)


# ---------- YEAR / DECADE ----------
df["year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year
df["decade"] = df["year"].apply(
    lambda year: f"{int(year) // 10 * 10}s" if pd.notna(year) else ""
)


# ---------- DOCUMENT ----------
df["document"] = df.apply(build_document, axis=1)


# ---------- DEDUPLICATE ----------
df["_title_norm"] = df["title"].str.lower().str.strip()
df["_year_norm"] = df["year"].fillna(0).astype(int)

before = len(df)
df = df.drop_duplicates(subset=["_title_norm", "_year_norm"], keep="first")
df = df.drop(columns=["_title_norm", "_year_norm"])

print(f"  Dropped {before - len(df):,} title/year duplicates")


# ---------- FINAL SAFETY CHECKS ----------
df = df[df["document"].str.len() > 0]
df = df.reset_index(drop=True)

required_output_columns = [
    "id",
    "title",
    "vote_average",
    "vote_count",
    "status",
    "release_date",
    "runtime",
    "adult",
    "homepage",
    "original_language",
    "original_title",
    "overview",
    "popularity",
    "poster_path",
    "tagline",
    "genres",
    "production_companies",
    "spoken_languages",
    "keywords",
    "genres_clean",
    "keywords_clean",
    "year",
    "decade",
    "document",
]

df = df[required_output_columns]


# ---------- SAVE ----------
df.to_csv(OUTPUT_FILE, index=False)

print(f"\nOK Saved cleaned dataset to {OUTPUT_FILE}")
print(f"OK Final movie count: {len(df):,}")
print("\nSample document:")
print("-" * 60)
print(df.iloc[0]["document"])
print("-" * 60)
