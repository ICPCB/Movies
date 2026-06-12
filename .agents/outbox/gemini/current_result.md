The audit of dataset v6 is complete. I have inspected all 30 "falls in love" records in `training/plot_description.jsonl` and sampled 20 additional `plot_description` records and 15 `hybrid_queries`. 

**Findings:**
1.  **"Falls in love" Tropes:** All 30 records (including object-less and genre-prefixed variants) correctly keep "falls in love" verbatim in the gold `plot_elements`, adhering to rule 3.11.1. No gerunds or other inflections were found in the gold labels.
2.  **Subject NPs:** Subjects are extracted as atomic noun phrases (e.g., "vampire", "android", "knight") consistent with rule 3.8.
3.  **Settings:** Trailing settings (e.g., "in the deep sea", "in space", "in winter") are correctly extracted as separate plot elements (e.g., `["mermaid", "falls in love", "deep sea"]`), following the v6 shapes (a, b, c).
4.  **Genre Mapping:** Genre words in prefixes (e.g., "animated movie about...", "sci-fi movie about...") are correctly mapped to `genres_include` and excluded from `plot_elements`.
5.  **Adjective/Adjunct Rules:** Evaluative adjectives (e.g., "scrappy", "cozy") are correctly dropped (rule 3.11.2), while type-forming modifiers (e.g., "rookie cop", "hidden city") are preserved. Weather/manner adjuncts (e.g., "in the rain") are correctly dropped (rule 3.11.3).
6.  **Held-out Query:** Verified that the specific held-out query text "animated movie about a robot who falls in love in space" does not exist in the training dataset.
7.  **Quality:** All sampled records (including `plot_elements: ["firefighters", "wildfire"]` for "firefighters battling a wildfire") show precise atomic decomposition and natural phrasing.

VERDICT: PASS
