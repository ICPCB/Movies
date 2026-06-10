export default function Footer() {
  return (
    <footer className="mt-20 border-t border-night-600/40 py-8">
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-2 px-4 text-center text-xs text-fog-500 sm:px-6">
        <p>
          Runs entirely on your machine — search, ranking, and explanations are local.
        </p>
        <p>
          This product uses the TMDB dataset and image CDN. Powered by{" "}
          <span className="text-fog-400">TMDB</span> — not endorsed or certified by TMDB.
        </p>
      </div>
    </footer>
  );
}
