import { useSyncExternalStore } from "react";

/** Маршрутизация на History API: трёх экранов хватает без отдельной библиотеки. */

export type Route =
  | { name: "home" }
  | { name: "library" }
  | { name: "song"; id: string }
  | { name: "missing" };

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function parse(pathname: string): Route {
  if (pathname === "/" || pathname === "") return { name: "home" };
  if (pathname === "/library") return { name: "library" };
  const song = /^\/song\/([0-9a-f]{32})$/.exec(pathname);
  if (song?.[1]) return { name: "song", id: song[1] };
  return { name: "missing" };
}

export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path);
  window.scrollTo({ top: 0 });
  listeners.forEach((listener) => {
    listener();
  });
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname);
  return parse(pathname);
}
