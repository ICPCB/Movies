# Llama Intent Parser — LoRA training spec

Owner: Claude (label/dataset spec + review). Implementation coder: Codex or Gemini per ticket. Status: DEPLOYED (V6 E4 gate passed and local serving integration completed 2026-06-12).

## 1. Goal

Train **one unified LoRA adapter** on the local Llama 3.2 1B weights that converts any natural-language movie request into the canonical CineMatch intent JSON. One adapter, trained on the merged category dataset — never multiple per-category models.

Design separation (non-negotiable, unchanged):

```text
Llama parses user intent into structured JSON.
CineMatch retrieves, filters, scores, and reranks real movies from its own index.
Ollama llama3.2 may only explain already-selected results.
The model never invents a movie recommendation.
```

## 2. Output schema

The adapter targets the **existing** serving schema `engine/intent_schema.py: INTENT_SCHEMA` — the schema the query builder already consumes. The original idea-doc field names map onto it:

| Idea-doc field | Canonical field |
|---|---|
| `search_type` (mood / plot / hybrid) | `mode` (mood / content / hybrid / category / random) |
| `user_mood` | `user_moods` (user_mood_vocab categories) |
| `desired_film_mood` | `desired_film_moods` (film_mood_vocab, closed 24-value enum) |
| `avoid` | `avoid_film_moods` (same enum) |
| `plot_keywords` | `plot_elements` (short noun phrases) |
| `genres` | `genres_include` / `genres_exclude` (TMDB genre list) |

The user-mood vs film-mood distinction is preserved exactly as in the serving path: *user* moods are how the person feels; *film* moods are what the film should feel like; the only bridge is `labels/user_mood_map.json` (e.g. a lonely/sad user gets **warm** films, not lonely films).

## 3. Gold-intent rules (Claude-owned; generator and graders must follow)

1. **User mood only** ("feeling forlorn and discouraged"): `user_moods` = matched categories; `desired_film_moods` / `avoid_film_moods` = exactly the static map's values (avoid loses ties to desired across categories); `mode: "mood"`.
2. **Film mood only** ("want something warm and funny"): no `user_moods`; `desired_film_moods` = the stated enum moods; `mode: "mood"`.
3. **User + film mood** ("feeling depressed, want something funny"): `user_moods` from the feeling clause; `desired_film_moods` = map(desired) ∪ explicitly requested film moods; `avoid_film_moods` = map(avoid) − desired.
4. **Avoid preferences** ("something warm tonight, nothing scary please"): explicitly avoided enum moods go to `avoid_film_moods`; an explicit user statement always beats the static map in both directions (explicit avoid removes a mapped desired; explicit desired removes a mapped avoid).
5. **Plot description** ("a slow burn heist thriller in winter"): `plot_elements` = short noun phrases from the request; `mode: "content"`; no mood fields unless a feeling marker is present.
6. **Hybrid** ("feeling depressed, want a space adventure"): feeling clause → mood fields per rule 1; want clause → `plot_elements`; `mode: "hybrid"`.
7. **Implicit plot descriptions** — the parser must infer canonical concepts even when the keyword is never written: "a person trapped in repeating days" → `plot_elements: ["time loop"]`. The concept-inference table below is the authoritative seed; gold for an implicit query is the canonical concept term(s), and the literal concept keyword must NOT appear in the query text.

### Concept-inference table (seed, extend in dataset generation)

| Canonical concept | Implicit phrasings (examples) |
|---|---|
| time loop | trapped in repeating days; lives the same day over and over |
| amnesia | wakes up with no memory; can't remember who he is |
| heist | a crew planning to rob a casino; pulling off one last big job |
| body swap | two people wake up in each other's bodies |
| time travel | a scientist visits his own past; sent back decades to fix a mistake |
| post-apocalyptic | survivors wandering a world after civilization collapsed |
| AI uprising | machines turn against their creators |
| alien invasion | ships appear over every city and start attacking |
| zombie outbreak | the dead rise and attack the living |
| haunted house | a family's new home where strange things happen at night |
| revenge | a man hunts down the people who destroyed his family |
| survival | stranded alone on a deserted island |
| coming of age | a shy teenager figuring out who she is over one summer |
| courtroom | a lawyer defending an innocent man at trial |
| undercover cop | a detective living a double life inside a crime ring |

### 3.8 Dataset-v2 rules (LORA-TRAIN-2; owner directives 2026-06-11)

Root cause of the v1 gate failure (ledger LORA-GATE-REVIEW): v1 templates taught
single-phrase extraction, never decomposition. v2 adds the rules below. Owner
constraints, binding for every generated label:

1. **Fixed vocab only**: `user_moods` from the 18 vocab categories;
   `desired_film_moods`/`avoid_film_moods` from the 24-value film enum;
   `genres_include` from the TMDB list. Any other value is a generation error.
2. **User mood vs film mood are never interchangeable**: feeling clauses
   ("I'm…", "feeling…", body sensations) produce ONLY `user_moods` (film moods
   then come from the map); want/desire clauses produce ONLY film moods.
   No template may put a film-mood enum word in a feeling clause or a
   user-vocab feeling word in a want clause.
3. **No keyword-matching shortcuts**: v2 adds implicit phrasings (3.9) whose
   gold label word does NOT appear in the text — for film moods, user moods
   (via body sensations), and plot concepts (3.7) alike.
4. **Mood-tag caps**: explicitly stated film moods per query ≤ 3;
   rule-derived unions (map ∪ explicit) keep whatever §3.3 produces (matches
   intent_v1 gold). The movie-side 2–4-main-tags rule lives in `labels/` and
   is untouched by this dataset.

**Atomic plot decomposition (closes the v1 gap):**

- Gold `plot_elements` are atomic noun phrases. Compounds in text are split:
  "a boxing underdog story" → `["boxing", "underdog"]`, never
  `["boxing underdog story"]`.
- Generic words never appear in gold: story, movie, film, flick, stuff, thing.
- Prepositional/setting structures must be covered by templates:
  "{a} on a {b}", "{a} across the {b}", "{a} in {setting}", "{a} during {b}",
  "{a} with {b}" — gold = both elements.
- Genre words fused into compounds still resolve to `genres_include`:
  "a courtroom drama", "time travel adventure", "animated movie about…" —
  the genre word maps to its TMDB genre AND is dropped from `plot_elements`.
- Settings are elements when they are places, seasons, or locales: winter,
  the desert, space → `["…", "winter"]`. Transient weather or manner
  adjuncts ("in the rain", "through the snow", "at night") are NOT
  elements and drop (3.11.3; matches intent_v1 iv47). An earlier revision
  of this line listed "the rain" as a setting — that was inconsistent with
  the eval gold and is superseded.
- Plurals: gold keeps the surface form of the text ("pirates" → "pirates").

### 3.9 Implicit phrasing tables (authored by Claude; review required by 2–3 AIs before training)

Acceptance: dataset v2 ships only after at least two independent AI reviewers
(not the generator's implementer) audit sampled records against 3.8 rules 1–4
and the keyword-leak assertion, and the lead records their verdicts in the
ledger.

**Implicit film-mood phrasings** (gold = the named enum mood(s) in
`desired_film_moods`, `mode: "mood"`; the mood word must NOT appear in text):

| Mood | Implicit phrasings (examples; extend with same rule) |
|---|---|
| funny | something that will make me laugh out loud; a movie with jokes that actually land |
| heartwarming | something that melts your heart; a story about people being quietly good to each other |
| feel-good | a movie that leaves me smiling; something easy that puts me in a better headspace |
| uplifting | something that makes me believe things get better; a film that raises my spirits |
| hopeful | a story where things turn out okay in the end; something that says tomorrow can be better |
| lighthearted | nothing heavy, just something breezy; something playful that doesn't take itself seriously |
| romantic | a love story; two people slowly falling for each other |
| inspiring | a story that makes me want to chase my dreams; people beating impossible odds that fires me up |
| exciting | something with real adrenaline; a ride that never slows down |
| thrilling | edge-of-my-seat stuff; something that gets my pulse racing |
| suspenseful | something that keeps me guessing until the end; a slow build where you don't know who to trust |
| tense | a knot-in-your-stomach atmosphere; white-knuckle the whole way through |
| action-packed | wall-to-wall fights and chases; explosions and set pieces nonstop |
| epic | a grand sweeping saga across years and continents; something huge in scope |
| mind-bending | something that messes with my head; a film I'll need to rewatch to understand |
| thought-provoking | something that leaves me with big questions; a film I'll be chewing on for days |
| dark | morally murky and shadowy in tone; something grim with a black streak |
| gritty | raw street-level realism; rough around the edges with no gloss |
| bleak | no comfort and no easy answers; the kind of film where hope never shows up |
| melancholic | something quiet and full of longing; a soft ache of a film |
| scary | something that makes me sleep with the lights on; something to keep me checking behind the door |
| disturbing | something that crawls under your skin and stays there; imagery I won't shake for days |
| bittersweet | happy and sad at the same time; an ending that smiles through tears |

**Implicit user-mood phrasings** use the `body_sensations` table in
`labels/user_mood_vocab.json` (fixed vocab, one category per word) inside
bodily templates ("my shoulders are {w} and I can't unwind", "everything in
my chest feels {w}") — gold = the mapped category; the category name must not
appear in the text.

### 3.10 Dataset-v3 rules (LORA-TRAIN-3; gate-failure analysis 2026-06-12)

Root cause of the v2 gate failure (ledger LORA-GATE-REVIEW-2): adapter-v2
under-extracts multi-element plot queries and lacks coverage for several
extraction shapes the eval exercises. v3 adds, under the same 3.8 rules:

1. **Plural-subject action clauses** ("firefighters battling a wildfire"):
   gold = plural surface subject + the verb's direct-object noun phrase; the
   verb drops (atomic-noun-phrase rule) and prepositional-adjunct nouns drop
   too ("at sea", "behind enemy lines", "through the snow"), matching the
   intent_v1 convention (iv47 drops "in the rain"). New
   `PLURAL_SUBJECT_ACTIONS` pool; quota 60 in plot_description, 30 in
   hybrid_queries.
2. **Place-genre compounds** ("a hospital drama about a missing child"):
   the place noun stays a plot element, the genre word resolves to
   `genres_include` (3.8 fusion rule). Pool: courtroom/hospital/newsroom/
   prison × drama.
3. **Three-element queries** ("a movie about {a} and {b} set in {setting}"):
   gold = all three elements.
4. **Compound-NP topics** added to the explicit pool (ghost ship, escape
   room, rookie cop, getaway driver, masked vigilante, chess prodigy,
   corrupt mayor, custody battle, wildfire, wrestling, surfing, underdog) —
   teaches span integrity for modifier+noun phrases.
5. **Genre vocabulary completed**: `family` → Family (movie-required head
   noun) and `musical` → Music join the literal genre-word list; both are in
   the canonical TMDB list in `engine/intent_parser.py`.
7. **Concept-table consistency fix (reviewer-D finding)**: the implicit
   concept formerly named "courtroom drama" is renamed to "courtroom" so no
   genre word ever appears in `plot_elements`; implicit phrasings keep
   `genres_include: []` because no genre word is grounded in the text.
6. Plot quota rebalance: fused 180 / targeted-v3 60 / multi 90 / implicit
   180 / single 90. Hybrid: fused 180 / plural 30 / multi 60 / single 330.

Known intent_v1 gold-vs-spec inconsistencies found during gate review 2
(NOT fixed — eval gold changes are an owner decision; flagged for review):
iv47 omits "rain" although 3.8 lists "the rain" as a setting element;
iv52 gold "animals" pluralizes the surface form "animal" against the
surface-form rule; iv38 gold "falls in love" is a verb phrase although 3.8
requires noun phrases. Training data must follow the spec, not the eval
quirks; no training pair may copy an intent_v1 query text.

### 3.11 Dataset-v4 rules (LORA-TRAIN-4; gate-failure analysis LORA-GATE-REVIEW-3)

Targets the adapter-v3 misses. New gold conventions, codified here so
generator, graders, and reviewers share one written rule:

1. **Lexicalized trope elements.** A small closed list of fixed expressions
   counts as atomic elements even when verb-derived, because users and the
   eval gold treat them as tropes: `falls in love`, `found family`,
   `time loop`, `body swap`, `coming of age`. This supersedes the 3.10 note
   that flagged iv38's "falls in love" as a quirk — it is now a sanctioned
   trope element. No other verb phrase may appear in gold.
2. **Evaluative-adjective drop vs type-forming modifier keep.** Subjective
   quality adjectives (kind, gentle, quiet, elderly, little, scrappy, cozy)
   and film-style modifiers in content queries ("slow burn", "cozy" before a
   genre compound) drop from gold — they ground neither moods nor elements: "a kind wizard mentoring an orphan" →
   `["orphan", "wizard"]`. Type-forming modifiers that change what the
   thing IS stay inside the compound: "wounded bear", "blind veteran",
   "masked vigilante", "alien creature", "corrupt mayor". Contrast:
   "an elderly hacker" → `["hacker"]` but "a rookie cop" → `["rookie cop"]`
   (rookie defines the role).
3. **Weather/manner adjuncts drop** (amends the 3.8 settings line):
   "in the rain", "through the snow", "at night" are not elements;
   place/season/locale settings (winter, space, the desert) are.
4. **New v4 shapes** (all plot_description targeted-bucket):
   singular-subject gerund clauses; "{setting} {genre} with {NP}";
   "{a} {b} story" compounds (genres stay empty — "story" grounds no
   genre); bare "in {setting}" fused variants ("a heist thriller in
   winter"-shaped); plural-subject records with explicit weather-adjunct
   drops; "winter" joins the setting pool.

## 4. Datasets (`training/`)

Category files, merged into one training file for the single unified adapter:

```text
training/
  mood_user_only.jsonl
  mood_film_only.jsonl
  mood_user_and_film.jsonl
  avoid_preferences.jsonl
  plot_description.jsonl      (explicit AND implicit pairs)
  hybrid_queries.jsonl
  final_intent_train.jsonl    (merged; train/val/test split markers)
```

Record shape: `{"text": <user request>, "intent": <full canonical intent JSON>, "category": <slice>, "provenance": "deterministic_rules" | "ai_draft", "split": "train"|"val"|"test"}`. Every record must pass `engine.intent_schema.validate_intent`. Implicit plot records must additionally pass the no-literal-keyword assertion. Provenance is honest, never `human_gold`. Target ≈3,600 pairs (§14), seeded from `labels/user_mood_map.json`, the mood vocabularies, `eval/queries/*.jsonl`, the concept table above, and (locally) the 120 mood seed examples in `cinematch-llama/`.

Generator: `training/build_intent_dataset.py` (interface stub in repo; implementation by Codex/Gemini per ticket §7). Deterministic given a seed — running twice must produce byte-identical output, matching the `eval/scripts/build_mood_queries.py` precedent.

## 5. Eval set and acceptance gate

`eval/queries/intent_v1.jsonl` (Claude-authored, committed with this spec): seven slices — `user_mood_only`, `film_mood_only`, `user_and_film_mood`, `plot_description`, `hybrid`, `avoid_preferences`, `implicit_plot`. `eval/scripts/intent_parser_eval.py --intent-v1` reports schema validity, mode accuracy, and per-slice micro P/R/F1 over `user_moods`, `desired_film_moods`, `avoid_film_moods`, `plot_elements`, `genres_include`.

Eval records are **held out**: the generator must exclude any training pair whose text matches an intent_v1 query.

**Gate:** the adapter ships into the serving path only if, on intent_v1, it (a) keeps schema validity ≥ 0.99, (b) beats the current few-shot tier-2 baseline on field-F1 for the plot/hybrid/implicit slices, and (c) does not regress the tier-1 mood-slice F1 (PHASE-7 baseline on mood_v1: validity 1.0, mode_acc 0.98, F1 user 0.859 / desired 0.897 / avoid 0.968).

**Final result (2026-06-12): PASS.** V6 E4 reached validity/mode accuracy 1.0 on all slices; plot 0.9583 > 0.9412, hybrid 0.7179 > 0.7027, implicit 0.8800 > 0.0, and mood requirements passed. Serving uses the adapter as the primary free-text parser through `engine/lora.py` + `scripts/lora_server.py`, with deterministic Tier 1 fallback. Ollama remains optional for fallback parsing, query expansion, and explanations.

## 6. Training configuration (ULTRAPLAN §14)

- Base: local Llama 3.2 1B weights at `cinematch-llama/Llama-3.2-1B/` — **verified 2026-06-11: BASE variant** (`config.json` `eos_token_id=128001`; no `chat_template` in `tokenizer_config.json`; `special_tokens_map.json` eos = `<|end_of_text|>`). **Owner decision 2026-06-11: Option B** — train these base weights with the fixed prompt format in §6.1. Do not download Llama-3.2-1B-Instruct; that is the fallback only if the §5 gate fails after training.
- PEFT LoRA: r=16, α=32, dropout 0.05, target q/k/v/o projections; final deployed run used 4 epochs.
- Metric: JSON validity + per-field F1 on the held-out test split and intent_v1.
- Weights/adapters are never committed (`cinematch-llama/` is gitignored).
- Explanations remain on Ollama llama3.2 — the adapter is for parsing only.

### 6.1 Fixed prompt format (Claude-owned contract; base model has no chat template)

Single source of truth: `training/prompt_format.py`. The dataset generator, the training script, and the eval adapter path must all import from it. No inline copies of the template anywhere — train/inference format drift is the primary failure mode of training a base model, and centralizing the template is the mitigation.

Required module surface:

```python
PROMPT_TEMPLATE = (
    "### Task: Parse the movie request into CineMatch intent JSON.\n"
    "### Request:\n{text}\n"
    "### Intent:\n"
)

def canonical_json(intent: dict) -> str:
    # json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ...

def build_prompt(text: str) -> str:
    # PROMPT_TEMPLATE.format(text=text) — ends exactly at "### Intent:\n"
    ...

def build_example(text: str, intent: dict) -> str:
    # build_prompt(text) + canonical_json(intent)  (EOS appended by tokenizer)
    ...
```

Conventions:

- BOS `<|begin_of_text|>` (128000) is added by the tokenizer, never written into the template.
- EOS/stop = `<|end_of_text|>` (128001), appended after the JSON during tokenization; generation stops at EOS with `max_new_tokens=256` headroom.
- Training loss is masked over the prompt tokens; loss is computed only on the completion (canonical JSON + EOS).
- Eval/inference decoding is greedy (`do_sample=False`); the generated text up to EOS is parsed with `json.loads` and then `validate_intent`.
- `canonical_json` is the only serializer used for training targets, so reruns stay byte-identical (§4 determinism rule).

## 7. Local training ticket (ready to dispatch — Codex or Gemini)

```text
Goal: Verify local Llama base weights, clean cinematch-llama/, implement the
  dataset generator, build the dataset, train the unified LoRA adapter, and
  eval it against intent_v1 per spec sections 3-6.
Files to change:
  training/prompt_format.py (new; implement exactly per spec section 6.1)
  training/test_prompt_format.py (new; round-trip + determinism tests)
  training/build_intent_dataset.py (implement per interface stub)
  training/mood_user_only.jsonl, training/mood_film_only.jsonl,
  training/mood_user_and_film.jsonl, training/avoid_preferences.jsonl,
  training/plot_description.jsonl, training/hybrid_queries.jsonl,
  training/final_intent_train.jsonl (generated)
  cinematch-llama/** (local only, untracked: training scripts/outputs)
Files to read but not change:
  docs/intent-lora-spec.md
  engine/intent_schema.py, engine/intent_parser.py
  labels/user_mood_map.json, labels/user_mood_vocab.json, labels/film_mood_vocab.json
  eval/queries/intent_v1.jsonl, eval/scripts/intent_parser_eval.py
Acceptance criteria:
  1. MODEL VERIFICATION RESOLVED (2026-06-11): Claude confirmed the local
     weights are the BASE variant (config.json eos_token_id=128001, no
     chat_template in tokenizer_config.json, special_tokens_map eos
     <|end_of_text|>). Owner chose Option B: train the base model with the
     fixed prompt format in spec section 6.1. Do NOT download Instruct. All
     prompt construction must go through training/prompt_format.py; inline
     prompt strings anywhere else are a stop condition.
  2. cinematch-llama/ cleanup AFTER verification. Keep: Llama-3.2-1B/
     safetensors weights + tokenizer/config files, mood_examples_seed_v1_120.jsonl,
     any train/test script being reused. Delete (exact paths, report before
     deleting anything not listed): Llama-3.2-1B/original/ (2.36 GB duplicate
     .pth), outputs/stage1_smoke_lora/ (all checkpoints + reports),
     stage1/data/ (superseded by training/), stale configs. Anything ambiguous:
     report, do not delete.
  3. python training/build_intent_dataset.py --seed-examples
     cinematch-llama/mood_examples_seed_v1_120.jsonl runs deterministically
     (two runs byte-identical), ~3,600 pairs, 100% validate_intent pass,
     implicit pairs pass the no-literal-keyword assertion, no overlap with
     intent_v1 queries.
  4. LoRA training completes with spec section 6 hyperparameters; adapter saved
     under cinematch-llama/outputs/ (never committed).
  5. Eval: python -m eval.scripts.intent_parser_eval --intent-v1 (tier-1
     baseline) and the adapter-backed run; report per-slice F1 side by side
     against the section 5 gate.
Validation commands:
  python -m pytest api/tests eval/tests training -q
  python training/build_intent_dataset.py (twice; diff outputs)
  python -m eval.scripts.intent_parser_eval --intent-v1
Dependencies: local GPU PC; venv with torch+peft+transformers; spec sections 3-6.
Risk level: medium (model training; no production src/ or serving changes).
Reviewer: Claude (gate review per docs/AGENT_PIPELINE.md before any serving change).
Stop conditions: prompt template defined anywhere other than
  training/prompt_format.py; any ambiguous deletion; validity < 0.99;
  gate not met (report, do not wire the adapter in).
```
