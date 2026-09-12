/**
 * The one-shot reveal that shows a consequence travelling.
 *
 * A cascade is a claim about causation -- the event did this to that water,
 * which did this to those routes, which did this to these hulls. Showing all of
 * it at once would be a state change; showing it in order is the explanation.
 * So `reveal` walks 0 to 1 across roughly a second and a half and then stops.
 *
 * It stops deliberately. A control room whose map pulses forever is a control
 * room where the pulsing stops meaning anything, and the state after the reveal
 * is the state an operator has to be able to read for the next twenty minutes.
 *
 * Interpolation happens here, over quantities the server already computed. The
 * frame loop never recomputes consequence and never refetches; it advances one
 * number that the layer builders read.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Long enough to read as motion, short enough not to be in the way. */
export const REVEAL_MS = 1600;

export interface CascadeReveal {
  /** 0..1. Layer builders take this and stage their own output from it. */
  reveal: number;
  playing: boolean;
  /** Run the reveal from the beginning. */
  play: () => void;
  /** Jump straight to the settled state, skipping the animation. */
  settle: () => void;
  /** Clear the world back to no cascade drawn. */
  reset: () => void;
}

export function useCascadeReveal(key: string | null): CascadeReveal {
  const [reveal, setReveal] = useState(0);
  const [playing, setPlaying] = useState(false);
  const frame = useRef<number | null>(null);
  const started = useRef<number>(0);

  const stop = useCallback(() => {
    if (frame.current !== null) {
      cancelAnimationFrame(frame.current);
      frame.current = null;
    }
  }, []);

  const play = useCallback(() => {
    stop();
    // Respect the viewer's own setting rather than overriding it: somebody who
    // has asked their system for reduced motion has asked for a reason.
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setReveal(1);
      setPlaying(false);
      return;
    }
    setPlaying(true);
    started.current = performance.now();
    const step = (now: number) => {
      const elapsed = now - started.current;
      const t = Math.min(1, elapsed / REVEAL_MS);
      // Ease-out: the consequence arrives quickly and settles, rather than
      // creeping at a constant rate like a progress bar.
      setReveal(1 - Math.pow(1 - t, 3));
      if (t < 1) {
        frame.current = requestAnimationFrame(step);
      } else {
        frame.current = null;
        setPlaying(false);
      }
    };
    frame.current = requestAnimationFrame(step);
  }, [stop]);

  const settle = useCallback(() => {
    stop();
    setPlaying(false);
    setReveal(1);
  }, [stop]);

  const reset = useCallback(() => {
    stop();
    setPlaying(false);
    setReveal(0);
  }, [stop]);

  // A new cascade replays; the same one re-rendering does not. Replaying on
  // every render would be the permanent pulsing this hook exists to avoid.
  useEffect(() => {
    if (!key) {
      reset();
      return;
    }
    play();
    return stop;
  }, [key, play, reset, stop]);

  return { reveal, playing, play, settle, reset };
}
