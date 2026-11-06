import { create } from "zustand";

export type Theme = "dark" | "light";

// Тот же ключ читает скрипт в index.html до первой отрисовки.
const STORAGE_KEY = "fretlines.theme";
const THEME_COLOR: Record<Theme, string> = { dark: "#0A0A0B", light: "#F2F1EE" };

function readStoredTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
}

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeState>()((set, get) => ({
  theme: readStoredTheme(),
  toggleTheme: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Приватный режим или запрет хранилища: тема просто не запомнится.
    }
    set({ theme: next });
  },
}));
