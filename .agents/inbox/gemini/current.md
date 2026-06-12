You are reviewer C (read-only) auditing dataset v6 of a LoRA training dataset before training. Repo root: current directory. Do NOT modify any file; inspection only.

Authoritative rules: docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md sections 3.8 (v2 gold rules), 3.11 (trope/adjective/adjunct conventions; 3.11.1 sanctions "falls in love" as a lexicalized trope element kept verbatim in gold).

Context: dataset v5 (3,600 records) passed a 2-AI panel and trained adapter v5, which missed the gate by one query (iv38 "animated movie about a robot who falls in love in space"). Dataset v6 changes ONLY the plot_description category: 30 quota-guaranteed "falls in love" trope records (in training/plot_description.jsonl, texts matching "falls in love"), adding three new shapes: (a) object-less clause with trailing setting ("a mermaid who falls in love in the deep sea" -> gold [mermaid, falls in love, deep sea]), (b) bare-start genre prefix ("animated movie about a puppet who falls in love in a circus" -> gold [puppet, falls in love, circus] + genres [Animation]), (c) the same for the existing with-object records. The implicit-plot quota dropped 180 -> 150 to fund the 30 slots; other categories regenerate under the same rules as v5 (only sampling/shuffle changed).

Your audit:
1. Read spec 3.8 and 3.11. Extract all 30 records containing "falls in love" from training/plot_description.jsonl and judge each gold against the spec: subject NP verbatim, "falls in love" verbatim (never gerund), trailing setting as its own element, genre word -> genres_include only (never in plot_elements), no eval-query text copied (the held-out query is "animated movie about a robot who falls in love in space" - confirm no training text equals it).
2. Sample ~20 other plot_description records and ~10 from one other category to confirm no regression in gold quality.
3. Flag any record whose text is not natural English a real user might type.
4. Report up to 10 concrete problem records verbatim (text + gold) if found.

End your reply with exactly one line:
VERDICT: PASS
or
VERDICT: FAIL - <one-line reason>
