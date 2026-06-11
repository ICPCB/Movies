# Ticket LORA-TRAIN-2d — reviewer-C round 2 fix: article agreement + genre head nouns

Goal:
Fix the remaining ungrammatical text generation found by the final dataset reviewer, then rebuild all dataset JSONL files deterministically. Three defect classes:
1. Article errors: "a exciting", "a epic", "a action-packed", "a animated", "a uplifting" (124 occurrences). Hard-coded "a {slot}" templates never use "an" before vowel-initial slot values.
2. Bare-genre-before-"about" errors: "want a animated about a con artist", "a action about a knight", "a horror about X", "a war about X". Genre words that are not standalone nouns need the head noun "movie".
3. Bad topic-genre compounds: "an assassin war set in a casino", "a robot action set in high school", "a samurai war set in summer camp". Same root cause in the fused-genre templates.

Current repo state:
main @ e861fb6, uncommitted v2 dataset work in training/ (already validated for vocab/leak/determinism; do not regress those). prompt_format.py is FROZEN.

Files to read but not change:
- docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md (sections 3.8, 3.9)
- training/prompt_format.py
- training/test_prompt_format.py
- labels/user_mood_vocab.json
- labels/film_mood_vocab.json
- labels/user_mood_map.json
- .agents/outbox/gemini/current_result.md (the reviewer FAIL report being fixed)

Files to change:
- training/build_intent_dataset.py
- training/final_intent_train.jsonl (rebuilt output)
- training/mood_user_only.jsonl (rebuilt output)
- training/mood_film_only.jsonl (rebuilt output)
- training/mood_user_and_film.jsonl (rebuilt output)
- training/avoid_preferences.jsonl (rebuilt output)
- training/plot_description.jsonl (rebuilt output)
- training/hybrid_queries.jsonl (rebuilt output)
- cinematch-llama/scripts/audit_dataset_v2.py (add regression checks only; keep existing checks)

Exact implementation rules:
1. Add a module-level helper in build_intent_dataset.py:
   `def _an(word: str) -> str: return f"an {word}" if word[0].lower() in "aeiou" else f"a {word}"`
2. Apply correct articles at every variable-slot site that currently hard-codes "a ":
   - FILM_MOOD_TEMPLATES line ~412 "I want a {m1} and {m2} movie" (article governed by m1)
   - FILM_MOOD_SINGLE_TEMPLATES line ~418 "give me a {m} movie"
   - USER_AND_FILM_TEMPLATES line ~427 "{feeling}, want a {m} movie"
   - PLOT_GENRE_TEMPLATES lines ~459-463: remove the broken third variant "an {g} movie about {p}" entirely; articles come from _an
   - HYBRID_GENRE_TEMPLATES lines ~497-500
   You may restructure these templates to take a pre-articled slot (e.g. "{ag} about {p}" where ag = _an(g)); keep template counts/distribution effects deterministic.
3. Define `MOVIE_REQUIRED_GENRES = {"animated", "action", "sci-fi", "crime", "war", "horror"}` (genre display words that cannot stand as bare nouns). All other GENRE_WORDS displays (comedy, drama, thriller, documentary, western, romance, adventure, mystery, fantasy) remain usable bare.
4. For "{g} about {p}" constructions (PLOT_GENRE_TEMPLATES, HYBRID_GENRE_TEMPLATES): when g is in MOVIE_REQUIRED_GENRES, always render "{g} movie about {p}" (e.g. "an animated movie about a con artist", "a war movie about a spy"). Bare-noun genres may keep both bare and "movie" variants.
5. For PLOT_FUSED_GENRE_TEMPLATE and HYBRID_FUSED_GENRE_TEMPLATE "{topic} {genre} set in {setting}": when genre is in MOVIE_REQUIRED_GENRES, render "{topic} {genre} movie set in {setting}" (e.g. "a robot action movie set in high school", "an assassin war movie set in a casino", "a vampire horror movie set in the deep sea").
6. Gold intents must be unchanged by these text edits except free_text_query mirroring the new text. Genre gold stays genres_include=[canonical]; "movie" is a head noun, never a plot element.
7. Do not change record counts, category caps, split ratios, seeds, or implicit-phrasing logic. Target: still 3,600 records, 600/category, 540/30/30 splits, byte-identical double build.
8. Extend cinematch-llama/scripts/audit_dataset_v2.py with three new checks over all record texts (report counts, nonzero = failure):
   a. regex `\ba [aeiou]` (article error)
   b. regex `\ban [^aeiou]` (reverse article error)
   c. regex `\b(animated|action|sci-fi|crime|war|horror) (about|set in)\b` (bare genre missing "movie")
9. Rebuild: run `venv\Scripts\python.exe training\build_intent_dataset.py` twice; outputs must be byte-identical.

Acceptance criteria:
- All three audit regexes return 0 matches across all training/*.jsonl.
- Zero occurrences of: "a exciting", "a epic", "a action", "a animated", "a uplifting", "an {g}" literal, "war set in", "action set in" (without "movie").
- Existing audit checks still pass: 0 nonsense prepositional compositions, 0 token leaks, 0 other-mood-word leaks, 180 implicit film-mood records.
- 3,600 records, 600/category, ratios assertions in the build script still pass.
- Double build byte-identical (Get-FileHash on all training/*.jsonl).
- `venv\Scripts\python.exe -m pytest training -q` passes.

Validation commands:
```
venv\Scripts\python.exe training\build_intent_dataset.py
venv\Scripts\python.exe cinematch-llama\scripts\audit_dataset_v2.py
venv\Scripts\python.exe -m pytest training -q
```
Plus the double-build hash comparison.

Dependencies: none beyond repo venv (no torch, no network, no model calls).
Risk level: low (text-template fix; no src/*, no serving, no training run).
Reviewer: Claude (lead) + Gemini reviewer-C re-audit afterwards.

Stop conditions:
- any edit outside the files-to-change list (prompt_format.py is FROZEN)
- any vocab value outside the fixed vocabularies
- determinism failure you cannot fix within scope
- no training/eval/model/network/Ollama calls, no deletions, no commits

Required final report format:
1. Verdict: PASS / FAIL / STOPPED / NEEDS_REVIEW
2. Files changed
3. Artifacts created
4. Validation commands and results (paste audit output)
5. Git status summary
6. Risks or caveats
7. Whether anything was committed (must be: nothing)
8. Exact next recommended step
