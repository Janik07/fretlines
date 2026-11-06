import { MotionConfig } from "motion/react";

import { CONTAINER, Header } from "./components/Header";
import { navigate, useRoute } from "./lib/router";
import { Home } from "./pages/Home";
import { Library } from "./pages/Library";
import { SongPage } from "./pages/SongPage";

export function App() {
  const route = useRoute();
  return (
    <MotionConfig reducedMotion="user">
      <div className="film-grain" aria-hidden="true" />
      {route.name === "home" && <Home route={route} />}
      {route.name === "library" && <Library route={route} />}
      {route.name === "song" && <SongPage key={route.id} id={route.id} route={route} />}
      {route.name === "missing" && (
        <>
          <Header route={route} />
          <main className={`${CONTAINER} py-24`}>
            <p className="font-display text-[clamp(64px,10vw,140px)] leading-[0.85] font-[820] uppercase">Тут тихо</p>
            <p className="mt-6 text-lead text-text-dim">Такой страницы нет. Вернёмся к музыке?</p>
            <button type="button" className="btn btn-primary mt-8" onClick={() => { navigate("/"); }}>
              На главную
            </button>
          </main>
        </>
      )}
    </MotionConfig>
  );
}
