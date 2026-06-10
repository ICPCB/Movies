import { MOOD_CATEGORIES } from "../data/moods";

interface MoodChipsProps {
  selected: string[];
  onToggle: (slug: string) => void;
}

export default function MoodChips({ selected, onToggle }: MoodChipsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {MOOD_CATEGORIES.map((category) => {
        const active = selected.includes(category.slug);
        return (
          <button
            key={category.slug}
            type="button"
            title={category.hint}
            onClick={() => onToggle(category.slug)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ${
              active
                ? "bg-gold-500 text-night-950 shadow-glow"
                : "bg-night-700/80 text-fog-300 ring-1 ring-night-500/60 hover:-translate-y-0.5 hover:text-snow"
            }`}
          >
            {category.label}
          </button>
        );
      })}
    </div>
  );
}
