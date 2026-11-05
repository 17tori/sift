/*
 * Motion tokens — single source for every animation in the app (motion/react).
 * Only transform / opacity are animated, plus clip-path on the one arch hero per screen.
 */
import type { Transition, Variants } from "motion/react";

export const ease = {
  /** Appearance: elements, count-up, photo reveal. */
  outExpo: [0.16, 1, 0.3, 1] as const,
  /** Movement: screen changes, morphs, layout. */
  inOut: [0.65, 0, 0.35, 1] as const,
  /** Slow ceremonial reveals of the gothic layer: splash, hero, payment seal. */
  ritual: [0.7, 0, 0.2, 1] as const,
};

export const dur = {
  micro: 0.12,
  element: 0.24,
  screen: 0.42,
  ritual: 0.8,
  ritualLong: 0.9,
  reduced: 0.15,
  photo: 0.5,
  shimmer: 1.4,
  scan: 1.6,
  breathe: 4,
} as const;

export const spring = {
  /** Sheets, cards, layout, hero. */
  soft: { type: "spring", stiffness: 260, damping: 30 } as const satisfies Transition,
  /** Presses, heart, stamp. */
  bouncy: { type: "spring", stiffness: 500, damping: 28 } as const satisfies Transition,
};

export const stagger = {
  cards: 0.04,
  cardsMax: 10,
  ledger: 0.06,
  typewriterChar: 0.012,
  typewriterLines: 3,
  bars: 0.05,
} as const;

export const press = { button: 0.97, card: 0.98 } as const;

export const t = {
  element: { duration: dur.element, ease: ease.outExpo } satisfies Transition,
  screen: { duration: dur.screen, ease: ease.inOut } satisfies Transition,
  ritual: { duration: dur.ritual, ease: ease.ritual } satisfies Transition,
  micro: { duration: dur.micro, ease: ease.outExpo } satisfies Transition,
  reduced: { duration: dur.reduced, ease: "linear" } satisfies Transition,
};

/** Delay for item i in a cascade; items past the cap appear without delay. */
export const cascadeDelay = (i: number, step: number = stagger.cards, cap: number = stagger.cardsMax) => (i < cap ? i * step : 0);

/** V. Result cards: y 16 → 0, opacity, stagger 40 ms over the first 10. */
export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number = 0) => ({ opacity: 1, y: 0, transition: { ...spring.soft, delay: cascadeDelay(i) } }),
};

/** III. Ledger rows of the analysis. */
export const ledgerVariants: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: (i: number = 0) => ({ opacity: 1, y: 0, transition: { duration: dur.element, ease: ease.outExpo, delay: i * stagger.ledger } }),
};

/** IV. Marketplace stamp lands like a seal. */
export const stampVariants: Variants = {
  idle: { scale: 1, rotate: 0, opacity: 1 },
  land: { scale: [1.15, 1], rotate: [-2, 0], opacity: [0, 1], transition: spring.bouncy },
};

/** Screen enter/exit. */
export const screenVariants: Variants = {
  initial: { opacity: 0, x: 24 },
  enter: { opacity: 1, x: 0, transition: t.screen },
  exit: { opacity: 0, x: -12, transition: { duration: dur.element, ease: ease.inOut } },
};

/** XIV. Error shake: 3 oscillations of 6 px. */
export const shake = { x: [0, -6, 6, -6, 6, -3, 0], transition: { duration: 0.36, ease: ease.inOut } };

/** XIII. Empty-state rosette breathing. */
export const breathe = {
  animate: { opacity: [0.6, 1, 0.6] },
  transition: { duration: dur.breathe, ease: ease.inOut, repeat: Infinity },
};

/** I. Splash wordmark rises through the arch mask. */
export const wordmarkReveal = {
  initial: { clipPath: "inset(100% 0% 0% 0%)", y: 12 },
  animate: { clipPath: "inset(0% 0% 0% 0%)", y: 0 },
  transition: { duration: 0.7, ease: ease.ritual },
};

/** Arch path in objectBoundingBox units; rect path has the same segment count so clip-path can morph. */
export const ARCH_PATH = "M0,1 L0,.42 C0,.18 .26,.04 .5,0 C.74,.04 1,.18 1,.42 L1,1 Z";
export const RECT_PATH = "M0,1 L0,0 C0,0 .26,0 .5,0 C.74,0 1,0 1,0 L1,1 Z";
