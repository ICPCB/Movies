// Generated from labels/user_mood_vocab.json + labels/user_mood_map.json (provenance:
// human_provided vocabulary, authored_static_table mapping). Keep in sync with those files;
// the UI never invents mood->film-mood mappings.

export interface MoodCategory {
  slug: string;
  label: string;
  hint: string;
  desired: string[];
  avoid: string[];
}

export const MOOD_CATEGORIES: MoodCategory[] = [
  {
    slug: "aliveness_joy",
    label: "Joyful",
    hint: "alive, energized, glowing",
    desired: ["feel-good", "funny", "exciting", "uplifting"],
    avoid: ["bleak"],
  },
  {
    slug: "connected_loving",
    label: "Loving",
    hint: "warm-hearted, close, tender toward someone",
    desired: ["romantic", "heartwarming", "warm"],
    avoid: ["disturbing"],
  },
  {
    slug: "curious",
    label: "Curious",
    hint: "intrigued, fascinated, wanting a puzzle",
    desired: ["mind-bending", "thought-provoking", "suspenseful"],
    avoid: [],
  },
  {
    slug: "hopeful",
    label: "Hopeful",
    hint: "expectant, optimistic, looking forward",
    desired: ["inspiring", "uplifting", "epic"],
    avoid: ["bleak"],
  },
  {
    slug: "grateful",
    label: "Grateful",
    hint: "appreciative, moved, fortunate",
    desired: ["heartwarming", "uplifting", "inspiring"],
    avoid: [],
  },
  {
    slug: "courageous_powerful",
    label: "Bold",
    hint: "daring, determined, ready for anything",
    desired: ["epic", "inspiring", "action-packed"],
    avoid: ["bleak"],
  },
  {
    slug: "accepting_open",
    label: "Open",
    hint: "calm, receptive, at peace",
    desired: ["thought-provoking", "warm", "uplifting"],
    avoid: ["disturbing"],
  },
  {
    slug: "tender",
    label: "Tender",
    hint: "soft, reflective, gently sentimental",
    desired: ["romantic", "warm", "bittersweet"],
    avoid: ["disturbing"],
  },
  {
    slug: "despair_sad",
    label: "Sad",
    hint: "heavy-hearted, grieving, down",
    desired: ["warm", "heartwarming", "hopeful", "uplifting"],
    avoid: ["bleak", "melancholic", "disturbing"],
  },
  {
    slug: "stressed_tense",
    label: "Stressed",
    hint: "wound up, overwhelmed, needing to exhale",
    desired: ["lighthearted", "funny", "feel-good", "warm"],
    avoid: ["tense", "dark", "disturbing"],
  },
  {
    slug: "angry_annoyed",
    label: "Frustrated",
    hint: "irritated, fed up, needing release",
    desired: ["action-packed", "exciting", "funny"],
    avoid: ["melancholic", "bleak"],
  },
  {
    slug: "fear",
    label: "Anxious",
    hint: "afraid, on edge, wanting safety",
    desired: ["warm", "lighthearted", "feel-good"],
    avoid: ["scary", "disturbing", "tense"],
  },
  {
    slug: "fragile",
    label: "Fragile",
    hint: "raw, delicate, easily bruised today",
    desired: ["warm", "heartwarming", "lighthearted"],
    avoid: ["disturbing", "scary", "bleak"],
  },
  {
    slug: "disconnected_numb",
    label: "Numb",
    hint: "distant, flat, hard to feel anything",
    desired: ["heartwarming", "exciting", "inspiring"],
    avoid: ["bleak", "melancholic"],
  },
  {
    slug: "powerless",
    label: "Powerless",
    hint: "stuck, small, out of options",
    desired: ["inspiring", "epic", "action-packed"],
    avoid: ["bleak", "disturbing"],
  },
  {
    slug: "embarrassed_shame",
    label: "Embarrassed",
    hint: "awkward, self-conscious, cringing",
    desired: ["funny", "lighthearted", "heartwarming"],
    avoid: ["dark", "disturbing"],
  },
  {
    slug: "guilt",
    label: "Guilty",
    hint: "remorseful, regretting something",
    desired: ["hopeful", "thought-provoking", "uplifting"],
    avoid: ["bleak"],
  },
  {
    slug: "unsettled_doubt",
    label: "Unsettled",
    hint: "uneasy, doubtful, second-guessing",
    desired: ["feel-good", "hopeful", "warm"],
    avoid: ["mind-bending", "disturbing"],
  },
];

export function moodsToIntentFields(slugs: string[]): {
  user_moods: string[];
  desired_film_moods: string[];
  avoid_film_moods: string[];
} {
  const selected = MOOD_CATEGORIES.filter((category) => slugs.includes(category.slug));
  const desired = new Set<string>();
  const avoid = new Set<string>();
  for (const category of selected) {
    category.desired.forEach((mood) => desired.add(mood));
    category.avoid.forEach((mood) => avoid.add(mood));
  }
  // A film mood explicitly desired by one selected feeling wins over another's avoid list.
  for (const mood of desired) avoid.delete(mood);
  return {
    user_moods: selected.map((category) => category.slug),
    desired_film_moods: [...desired].sort(),
    avoid_film_moods: [...avoid].sort(),
  };
}
