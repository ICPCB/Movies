interface PaginationProps {
  page: number;
  totalPool: number;
  pageSize: number;
  onPage: (page: number) => void;
  onReroll: () => void;
}

export default function Pagination({
  page,
  totalPool,
  pageSize,
  onPage,
  onReroll,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalPool / pageSize));
  return (
    <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className="rounded-full bg-night-700 px-4 py-2 text-sm font-medium text-fog-300 ring-1 ring-night-500/60 transition enabled:hover:text-snow disabled:opacity-40"
      >
        ← Prev
      </button>
      <span className="text-sm text-fog-400">
        Page <span className="font-semibold text-snow">{page}</span> of {totalPages}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        className="rounded-full bg-night-700 px-4 py-2 text-sm font-medium text-fog-300 ring-1 ring-night-500/60 transition enabled:hover:text-snow disabled:opacity-40"
      >
        Next →
      </button>
      <button
        type="button"
        onClick={onReroll}
        className="rounded-full bg-crimson-600/80 px-5 py-2 text-sm font-semibold text-snow ring-1 ring-crimson-500 transition hover:bg-crimson-500"
      >
        ⟳ Reroll
      </button>
    </div>
  );
}
