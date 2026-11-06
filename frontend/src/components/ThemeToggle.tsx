import { useReducedMotion } from "motion/react";
import { flushSync } from "react-dom";

import { useThemeStore } from "../store/theme";
import { Icon } from "./Icon";

export function ThemeToggle() {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const reduceMotion = useReducedMotion();
  const label = theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему";

  function handleClick() {
    const canCrossfade = reduceMotion !== true && typeof document.startViewTransition === "function";
    if (!canCrossfade) {
      toggleTheme();
      return;
    }
    // flushSync: новый снимок страницы должен уже содержать перерисованный React.
    document.startViewTransition(() => {
      flushSync(toggleTheme);
    });
  }

  return (
    <button type="button" onClick={handleClick} aria-label={label} title={label} className="icon-btn">
      <span className={`transition-transform duration-400 ease-film ${theme === "light" ? "rotate-180" : ""}`}>
        <Icon name="theme" size={18} />
      </span>
    </button>
  );
}
