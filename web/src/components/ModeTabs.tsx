export type SearchTab = "mood" | "content" | "category" | "random";

const TABS: { id: SearchTab; label: string; blurb: string }[] = [
  { id: "mood", label: "Mood", blurb: "How do you feel tonight?" },
  { id: "content", label: "Movie Description", blurb: "Describe the plot you want" },
  { id: "category", label: "Category", blurb: "Browse by genre or era" },
  { id: "random", label: "Random", blurb: "Spin the reel" },
];

interface ModeTabsProps {
  active: SearchTab;
  onChange: (tab: SearchTab) => void;
}

export default function ModeTabs({ active, onChange }: ModeTabsProps) {
  return (
    <div className="inline-flex rounded-full bg-night-800/80 p-1 ring-1 ring-night-500/50 backdrop-blur">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          title={tab.blurb}
          onClick={() => onChange(tab.id)}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all duration-200 sm:px-5 ${
            active === tab.id
              ? "bg-gold-500 text-night-950 shadow-glow"
              : "text-fog-400 hover:text-snow"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
