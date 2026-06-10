import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { HistoryItem, Intent } from "../lib/types";

const MODE_LABELS: Record<string, string> = {
  mood: "Mood",
  content: "Description",
  hybrid: "Hybrid",
  category: "Category",
  random: "Random",
};

export default function History() {
  const navigate = useNavigate();
  const [items, setItems] = useState<HistoryItem[] | null>(null);

  useEffect(() => {
    api.history
      .list()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  const rerun = (item: HistoryItem) => {
    try {
      const intent = JSON.parse(item.intent_json) as Intent;
      navigate("/", { state: { rerunIntent: intent } });
    } catch {
      navigate("/");
    }
  };

  const clear = async () => {
    await api.history.clear();
    setItems([]);
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <div className="flex items-center justify-between">
        <h1 className="animate-rise font-display text-3xl font-bold tracking-tight text-snow">
          Search history
        </h1>
        {items && items.length > 0 && (
          <button
            type="button"
            onClick={() => void clear()}
            className="rounded-full bg-night-700 px-4 py-1.5 text-xs font-medium text-fog-400 ring-1 ring-night-500/60 transition hover:text-crimson-500"
          >
            Clear all
          </button>
        )}
      </div>

      {!items ? (
        <div className="mt-8 space-y-2.5">
          {Array.from({ length: 5 }, (_, index) => (
            <div key={index} className="skeleton h-16 rounded-2xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="mt-8 rounded-2xl bg-night-800/70 px-5 py-10 text-center text-sm text-fog-500 ring-1 ring-night-600/50">
          No searches yet — your trail starts on the Discover page.
        </p>
      ) : (
        <ul className="mt-8 space-y-2.5">
          {items.map((item, index) => (
            <li
              key={item.id}
              className="animate-rise flex items-center gap-4 rounded-2xl bg-night-800/70 px-4 py-3 ring-1 ring-night-600/50 transition hover:ring-night-500"
              style={{ animationDelay: `${Math.min(index, 11) * 40}ms` }}
            >
              <span className="shrink-0 rounded-full bg-crimson-600/25 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-fog-300 ring-1 ring-crimson-500/30">
                {MODE_LABELS[item.mode] ?? item.mode}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-snow">
                  {item.query_text || <em className="text-fog-500">mood-only search</em>}
                </p>
                <p className="text-xs text-fog-500">
                  {new Date(item.created_at).toLocaleString()}
                </p>
              </div>
              <button
                type="button"
                onClick={() => rerun(item)}
                className="shrink-0 rounded-full bg-gold-500/15 px-4 py-1.5 text-xs font-semibold text-gold-400 ring-1 ring-gold-500/30 transition hover:bg-gold-500/25"
              >
                Run again
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
