import { motion } from "motion/react";
import { useId } from "react";

import { EASE_FILM } from "../lib/motion";

interface Option<T extends string> {
  value: T;
  label: string;
}

/** Переключатель-«таблетка»: выбранный пункт подсвечен плашкой, которая переезжает. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "md",
  fill = false,
}: {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  size?: "sm" | "md";
  /** На всю ширину: пункты делят место поровну (когда их много, а места мало). */
  fill?: boolean;
}) {
  const id = useId();
  const height = size === "sm" ? "h-8 text-[13px]" : "h-10 text-small";
  const spacing = fill ? "flex-auto px-2" : "px-3.5 sm:px-4";
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`${fill ? "flex w-full" : "inline-flex"} rounded-full border border-line bg-surface p-1`}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => {
              onChange(option.value);
            }}
            className={`relative ${height} ${spacing} rounded-full font-semibold whitespace-nowrap transition-colors duration-300 ease-film ${
              active ? "text-on-accent" : "text-text-dim hover:text-text"
            }`}
          >
            {active && (
              <motion.span
                layoutId={`seg-${id}`}
                className="absolute inset-0 rounded-full bg-accent"
                transition={{ duration: 0.35, ease: EASE_FILM }}
              />
            )}
            <span className="relative">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
