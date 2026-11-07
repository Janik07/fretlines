import { CONTAINER, Header } from "../components/Header";
import { useSong } from "../hooks/useApi";
import { navigate, type Route } from "../lib/router";
import { Processing } from "./Processing";
import { Studio } from "./studio/Studio";

export function SongPage({ id, route }: { id: string; route: Route }) {
  const { song, error, refresh } = useSong(id);

  if (!song) {
    return (
      <>
        <Header route={route} />
        <main className={`${CONTAINER} py-24`}>
          {error ? (
            <div className="max-w-lg">
              <p className="font-display text-display font-[800] uppercase">Не открывается</p>
              <p className="mt-4 text-body text-text-dim">{error}</p>
              <button type="button" onClick={() => { navigate("/library"); }} className="btn btn-ghost mt-8">
                К моим разборам
              </button>
            </div>
          ) : (
            <p className="pulse-soft font-display text-display font-[800] uppercase text-text-dim">Открываю…</p>
          )}
        </main>
      </>
    );
  }
  if (song.status === "done") return <Studio key={song.id} song={song} route={route} onRefresh={refresh} />;
  return <Processing song={song} route={route} onRetry={refresh} />;
}
