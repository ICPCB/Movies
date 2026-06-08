---
ticket_id: 8-F
phase: 8
depends_on: [7-D]
human_gate: no
status: READY
---

1. Goal
   Add 5 multi-constraint stress test queries (q61-q65) to
   eval/queries/all.jsonl. Update _schemas.py QUERY_IDS_V2 to
   include q61-q65.

2. Current repo state
   all.jsonl has 60 queries (q01-q60). QUERY_IDS_V2 = q01-q60.

3. Files to read
   eval/queries/all.jsonl
   eval/scripts/_schemas.py

4. Files allowed to change/create
   eval/queries/all.jsonl
   eval/scripts/_schemas.py (QUERY_IDS_V2 range only)

5. Files forbidden to change
   src/*, eval/scripts/compute_metrics.py, eval/scripts/error_report.py,
   eval/scripts/merge_labels.py

6. Exact implementation rules
   6a. Update QUERY_IDS_V2 in _schemas.py:
       QUERY_IDS_V2 = {f"q{i:02d}" for i in range(1, 66)}

   6b. Add 5 queries to all.jsonl:

   q61: Genre transition + negative constraints
   "I am looking for a bright colorful movie that looks exactly like a
   lighthearted family comedy about a summer vacation but it slowly turns
   into a deeply psychological thriller about isolation and losing your
   mind with absolutely no actual ghosts no monsters and no blood just
   pure existential dread and it should feature a lot of jazz music"
   tags: era: null, genre: ["thriller","comedy"], vocab_distance: high,
         length: long, specificity: high, ambiguity: high, mood: null
   notes: "Stress-test: genre transition + negative constraints + aesthetic."

   q62: Tonal paradox
   "a movie that feels like a warm hug for the first hour then
   punches you in the gut and leaves you staring at the ceiling
   questioning everything but in a beautiful way"
   tags: era: null, genre: ["drama"], vocab_distance: high,
         length: long, specificity: low, ambiguity: high, mood: null
   notes: "Stress-test: tonal shift + abstract emotional description."

   q63: Extreme negative constraint
   "a war movie with no battle scenes no explosions no guns just the
   silence between letters home and the weight of waiting"
   tags: era: null, genre: ["drama"], vocab_distance: high,
         length: medium, specificity: medium, ambiguity: high, mood: null
   notes: "Stress-test: genre + multiple exclusions + poetic phrasing."

   q64: Sensory/aesthetic
   "a visually stunning movie where every frame looks like a painting
   with minimal dialogue and a haunting orchestral score set in a
   decaying European city"
   tags: era: null, genre: ["drama","other"], vocab_distance: high,
         length: long, specificity: medium, ambiguity: high, mood: null
   notes: "Stress-test: visual + audio aesthetic + setting constraint."

   q65: Contradictory mood + content
   "I am feeling really happy and energized today and I want a movie
   that will absolutely destroy me emotionally like completely wreck
   me in the best way possible"
   tags: era: null, genre: ["drama"], vocab_distance: medium,
         length: long, specificity: low, ambiguity: high,
         mood: {current_emotion: "bored", desired_direction: "help_me_cry",
                energy_level: "emotional_but_safe",
                intensity: "heavy_but_requested",
                safety_sensitivity: "neutral"}
   notes: "Stress-test: positive state + intentional heavy content request."

   6c. Validate all 65 queries pass schema:
       .\venv\Scripts\python.exe -c "
       from eval.scripts._schemas import validate_query_record_v2
       from eval.scripts.compute_metrics import _read_jsonl
       from pathlib import Path
       for r in _read_jsonl(Path('eval/queries/all.jsonl')):
           validate_query_record_v2(r)
       print('All 65 queries valid')
       "

7. Acceptance criteria
   - all.jsonl has 65 queries
   - QUERY_IDS_V2 includes q61-q65
   - All queries pass validate_query_record_v2
   - All existing tests pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v
   .\venv\Scripts\python.exe -c "from eval.scripts._schemas import validate_query_record_v2; from eval.scripts.compute_metrics import _read_jsonl; from pathlib import Path; qs=list(_read_jsonl(Path('eval/queries/all.jsonl'))); assert len(qs)==65, f'Expected 65, got {len(qs)}'; [validate_query_record_v2(r) for r in qs]; print('PASS: 65 queries valid')"

9. Stop conditions
   - Existing queries modified -> HARD STOP
   - src/* modified -> HARD STOP
   - Schema validation fails -> FAIL

10. Required final report format
    Verdict:
    Queries added: q61-q65 summaries
    Schema validation:
    Next: 8-G
