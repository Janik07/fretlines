import type { Variants } from "motion/react";

/** SPEC §2.4: медленно и мягко — cubic-bezier(0.2, 0.8, 0.2, 1), 250–400 мс. */
export const EASE_FILM: [number, number, number, number] = [0.2, 0.8, 0.2, 1];

/** Появление: проявка + сдвиг на 8 px. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_FILM } },
};

export const stagger: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.07 } },
};

export const page = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_FILM } },
  exit: { opacity: 0, transition: { duration: 0.25, ease: EASE_FILM } },
};
