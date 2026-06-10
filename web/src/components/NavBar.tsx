import { NavLink } from "react-router-dom";

const linkBase =
  "rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200";

function navClass({ isActive }: { isActive: boolean }) {
  return `${linkBase} ${
    isActive
      ? "bg-gold-500/15 text-gold-400"
      : "text-fog-400 hover:text-snow hover:bg-night-700/60"
  }`;
}

export default function NavBar() {
  return (
    <header className="sticky top-0 z-40 border-b border-night-600/40 bg-night-900/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 sm:px-6">
        <NavLink to="/" className="group flex items-baseline gap-0.5">
          <span className="font-display text-2xl font-bold tracking-tight text-snow">
            Cine
          </span>
          <span className="font-display text-2xl font-bold tracking-tight text-gold-500 transition-colors group-hover:text-gold-300">
            Match
          </span>
          <span className="ml-2 hidden text-[11px] uppercase tracking-[0.22em] text-fog-500 sm:inline">
            local picture house
          </span>
        </NavLink>
        <nav className="ml-auto flex items-center gap-1.5">
          <NavLink to="/" className={navClass} end>
            Discover
          </NavLink>
          <NavLink to="/library" className={navClass}>
            Library
          </NavLink>
          <NavLink to="/history" className={navClass}>
            History
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
