import { navigate, type Route } from "../lib/router";
import { Icon } from "./Icon";
import { ThemeToggle } from "./ThemeToggle";

export const CONTAINER = "mx-auto w-full max-w-[1320px] px-4 sm:px-8 lg:px-12";

/** Знак: четыре струны и палец на ладу — тот же, что на иконке вкладки. */
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <g stroke="var(--on-accent)" strokeWidth="1.5" strokeLinecap="round">
        <path d="M7 10h18" opacity=".3" />
        <path d="M7 14h18" opacity=".5" />
        <path d="M7 18h18" opacity=".75" />
        <path d="M7 22h18" />
      </g>
      <circle cx="19.5" cy="14" r="2.9" fill="var(--on-accent)" />
    </svg>
  );
}

function link(path: string) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(path);
  };
}

export function Header({ route, overlay = false }: { route: Route; overlay?: boolean }) {
  return (
    <header className={overlay ? "absolute inset-x-0 top-0 z-20" : "relative z-20 border-b border-line"}>
      <div className={`${CONTAINER} flex h-[72px] items-center justify-between`}>
        <a href="/" onClick={link("/")} className="flex items-center gap-3" aria-label="Fretlines — на главную">
          <Mark />
          <span className="font-display text-[26px] leading-none font-[750] tracking-[0.04em] uppercase">
            Fretlines
          </span>
        </a>
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Разделы">
          <a
            href="/library"
            onClick={link("/library")}
            aria-current={route.name === "library" ? "page" : undefined}
            className="flex h-10 items-center gap-2 rounded-full px-4 text-small font-semibold text-text-dim transition-colors duration-300 ease-film hover:text-text aria-[current=page]:text-text"
          >
            <Icon name="library" size={18} />
            <span className="hidden sm:inline">Мои разборы</span>
          </a>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
