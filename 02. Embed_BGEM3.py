import os
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
import chromadb
from tqdm import tqdm

# ---------- CONFIG ----------
INPUT_FILE = "data/movies_clean.csv"
CHROMA_DIR = "data/chroma_bgem3"
COLLECTION_NAME = "movies"
EMBEDDING_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32

# Safer default.
# If True, this script refuses to add embeddings into a non-empty Chroma DB.
# This prevents accidentally mixing old vectors with new cleaned data.
REQUIRE_EMPTY_COLLECTION = True


# ---------- HELPERS ----------
def safe_text(value):
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {"nan", "none", "null", "na"}:
        return ""

    return text


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clip_text(value, limit):
    return safe_text(value)[:limit]


# ---------- DEVICE ----------
if torch.cuda.is_available():
    device = "cuda"
    try:
        device_name = torch.cuda.get_device_name(0)
    except Exception:
        device_name = "Unknown CUDA device"
    print(f"CUDA available. Using GPU: {device_name}")
else:
    device = "cpu"
    print("CUDA not available. Using CPU.")


# ---------- LOAD CLEANED DATA ----------
if not os.path.exists(INPUT_FILE):
    raise FileNotFoundError(f"Missing cleaned data file: {INPUT_FILE}")

print("Loading cleaned movies...")
df = pd.read_csv(INPUT_FILE, low_memory=False)
print(f"  {len(df):,} movies loaded")


# ---------- VALIDATE ----------
required_columns = [
    "id",
    "title",
    "document",
    "genres",
    "genres_clean",
    "release_date",
    "year",
    "vote_average",
    "vote_count",
    "popularity",
    "poster_path",
    "overview",
    "tagline",
    "keywords_clean",
    "runtime",
    "original_language",
    "original_title",
]

missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    raise ValueError(f"movies_clean.csv is missing required columns: {missing_columns}")

df["document"] = df["document"].apply(safe_text)
df = df[df["document"] != ""].reset_index(drop=True)

print(f"  {len(df):,} movies with valid documents")


# ---------- LOAD MODEL ----------
print(f"Loading model: {EMBEDDING_MODEL}")
model = SentenceTransformer(EMBEDDING_MODEL, device=device)


# ---------- SETUP CHROMA ----------
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)

already_done = collection.count()
print(f"  Already in DB: {already_done:,}")

if REQUIRE_EMPTY_COLLECTION and already_done > 0:
    raise RuntimeError(
        f"Chroma collection is not empty: {already_done:,} vectors found.\n"
        f"Delete {CHROMA_DIR} before rebuilding embeddings."
    )


# ---------- PREPARE DATA ----------
documents = df["document"].tolist()

metadatas = []
ids = []

for _, row in df.iterrows():
    movie_id = safe_int(row["id"])

    if movie_id <= 0:
        continue

    metadatas.append(
        {
            "tmdb_id": movie_id,
            "title": clip_text(row["title"], 300),
            "original_title": clip_text(row["original_title"], 300),
            "original_language": clip_text(row["original_language"], 20),
            "genres": clip_text(row["genres"], 500),
            "genres_clean": clip_text(row["genres_clean"], 300),
            "release_date": clip_text(row["release_date"], 50),
            "year": safe_int(row["year"]),
            "runtime": safe_int(row["runtime"]),
            "vote_average": safe_float(row["vote_average"]),
            "vote_count": safe_int(row["vote_count"]),
            "popularity": safe_float(row["popularity"]),
            "poster_path": clip_text(row["poster_path"], 300),
            "overview": clip_text(row["overview"], 700),
            "tagline": clip_text(row["tagline"], 300),
            "keywords": clip_text(row["keywords_clean"], 500),
        }
    )

    ids.append(f"tmdb_{movie_id}")


if len(documents) != len(ids):
    raise RuntimeError(
        "Document count and ID count do not match. Check invalid movie IDs."
    )

if len(documents) == 0:
    raise RuntimeError("No documents to embed.")


# ---------- EMBED ----------
print(f"Embedding {len(documents):,} movies on {device}...")

for i in tqdm(range(0, len(documents), BATCH_SIZE)):
    batch_docs = documents[i : i + BATCH_SIZE]
    batch_meta = metadatas[i : i + BATCH_SIZE]
    batch_ids = ids[i : i + BATCH_SIZE]

    embeddings = model.encode(
        batch_docs,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=BATCH_SIZE,
        convert_to_numpy=True,
    ).tolist()

    collection.add(
        embeddings=embeddings,
        documents=batch_docs,
        metadatas=batch_meta,
        ids=batch_ids,
    )

print(f"\nOK Done. Total in DB: {collection.count():,}")
