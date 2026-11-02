import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link } from "@tanstack/react-router";
import { CHAPTERS, HOTSPOTS } from "./chapters";

const TourScene = lazy(() => import("./TourScene"));
const REPO = "https://github.com/RaghhavMalani/logistics-route-optimization";

export default function TourPage() {
  const scroll = useRef<HTMLDivElement>(null),
    progress = useRef(0);
  const pins = useRef<(HTMLButtonElement | null)[]>([]),
    fills = useRef<(HTMLSpanElement | null)[]>([]);
  const openPinRef = useRef<number | null>(null),
    popover = useRef<HTMLDivElement>(null);
  const popSize = useRef({ width: 248, height: 150 });
  const [chapter, setChapter] = useState(0),
    [displayed, setDisplayed] = useState(0);
  const [openPin, setOpenPin] = useState<number | null>(null),
    [reduced, setReduced] = useState(false);
  const [mounted, setMounted] = useState(false),
    [unavailable, setUnavailable] = useState(false);
  const closePin = useCallback(() => {
    openPinRef.current = null;
    setOpenPin(null);
  }, []);
  const onUnavailable = useCallback(() => {
    setUnavailable(true);
  }, []);
  const go = (index: number) => {
    const element = scroll.current;
    if (!element) return;
    element.scrollTo({
      top: (index / 5) * (element.scrollHeight - element.clientHeight),
      behavior: reduced ? "instant" : "smooth",
    });
  };
  const readScroll = useCallback(() => {
    const element = scroll.current;
    if (!element) return;
    const p = Math.max(
      0,
      Math.min(
        5,
        (element.scrollTop /
          Math.max(1, element.scrollHeight - element.clientHeight)) *
          5,
      ),
    );
    progress.current = p;
    setChapter(Math.round(p));
    fills.current.forEach((fill, i) => {
      if (fill)
        fill.style.transform = `scaleX(${Math.max(0, Math.min(1, p - i + 1))})`;
    });
  }, []);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    setMounted(true);
    media.addEventListener("change", update);
    const observer = new ResizeObserver(readScroll);
    if (scroll.current) observer.observe(scroll.current);
    readScroll();
    return () => {
      media.removeEventListener("change", update);
      observer.disconnect();
    };
  }, [readScroll]);
  useEffect(() => {
    closePin();
    if (reduced) {
      setDisplayed(chapter);
      return;
    }
    const timer = setTimeout(() => setDisplayed(chapter), 180);
    return () => clearTimeout(timer);
  }, [chapter, reduced, closePin]);
  useEffect(() => {
    if (openPin === null) return;
    const element = popover.current;
    const observer = new ResizeObserver((entries) => {
      const r = entries[0]?.target.getBoundingClientRect();
      if (r) popSize.current = { width: r.width, height: r.height };
    });
    if (element) observer.observe(element);
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        const index = openPinRef.current;
        closePin();
        if (index !== null) pins.current[index]?.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      observer.disconnect();
    };
  }, [openPin, closePin]);
  const c = CHAPTERS[displayed];
  return (
    <div
      className="pw-tour"
      data-webgl={unavailable ? "unavailable" : "available"}
      data-chapter={chapter}
      data-reduced-motion={reduced}
    >
      {mounted && !unavailable && (
        <Suspense fallback={null}>
          <TourScene
            progress={progress}
            reduced={reduced}
            pins={pins}
            openPin={openPinRef}
            popover={popover}
            popSize={popSize}
            closePin={closePin}
            onUnavailable={onUnavailable}
          />
        </Suspense>
      )}
      <a href="#tour-card" className="skip">
        Skip to chapter
      </a>
      <div
        className="scroller"
        ref={scroll}
        onScroll={readScroll}
        tabIndex={0}
        aria-label="Scroll through the miniature voyage"
      >
        {CHAPTERS.map((c) => (
          <section key={c.label} aria-label={`${c.label} chapter scenery`} />
        ))}
      </div>
      <header className="bar">
        <a
          href="#tour-start"
          className="mark"
          onClick={(e) => {
            e.preventDefault();
            go(0);
          }}
          aria-label="PortWatch X, back to start"
        >
          PortWatch <i>X</i>
        </a>
        <nav aria-label="Project">
          <Link to="/explore">Global intelligence</Link>
          <Link to="/research">Research evidence</Link>
          <a href={REPO} target="_blank" rel="noopener noreferrer">
            Source
          </a>
        </nav>
        <Link
          className="btn solid go"
          to="/login"
          aria-label="Open the role demos"
        >
          <span className="label-long">Open the</span> role demos{" "}
          <span aria-hidden="true">→</span>
        </Link>
      </header>
      {unavailable && (
        <p className="nogl" role="status">
          The 3D miniature needs WebGL, which is unavailable in this browser
          right now. The chapters still work as you scroll.
        </p>
      )}
      <div className="pins">
        {HOTSPOTS.map((h, k) => (
          <button
            type="button"
            className="pin"
            key={h.t}
            ref={(el) => {
              pins.current[k] = el;
            }}
            hidden
            aria-label={h.t}
            aria-expanded={openPin === k}
            aria-controls={openPin === k ? "tour-popover" : undefined}
            onClick={() => {
              const next = openPin === k ? null : k;
              openPinRef.current = next;
              setOpenPin(next);
            }}
          >
            +
          </button>
        ))}
      </div>
      {openPin !== null && (
        <div
          className="pop"
          id="tour-popover"
          role="region"
          aria-label={HOTSPOTS[openPin].t}
          ref={popover}
        >
          <b>{HOTSPOTS[openPin].t}</b>
          <span>{HOTSPOTS[openPin].d}</span>
          <button
            type="button"
            onClick={() => {
              const index = openPinRef.current;
              closePin();
              if (index !== null) pins.current[index]?.focus();
            }}
          >
            Close
          </button>
        </div>
      )}
      <article
        className="card"
        id="tour-card"
        tabIndex={-1}
        aria-live="polite"
        aria-atomic="true"
        data-changing={!reduced && chapter !== displayed}
      >
        <div className="kicker">{c.kicker}</div>
        {displayed === 0 ? <h1>{c.title}</h1> : <h2>{c.title}</h2>}
        <p>{c.body}</p>
        {c.facts.length > 0 && (
          <ul className="facts">
            {c.facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        )}
        {displayed === 0 && (
          <div className="hint">
            <span aria-hidden="true" />
            Scroll to follow the voyage
          </div>
        )}
        {displayed === 2 && (
          <>
            <dl className="stats">
              <div className="stat">
                <dt>Mean regret</dt>
                <dd>
                  <s>12.14 h</s> → <b>1.05 h</b>
                </dd>
              </div>
              <div className="stat">
                <dt>p90 regret</dt>
                <dd>
                  <s>42.1 h</s> → <b>0.0 h</b>
                </dd>
              </div>
            </dl>
            <p className="note">
              Original historical synthetic benchmark: robust policy versus
              expected-value ranking, 200 vessel cases (10 unscored). Not
              measured shipping savings.{" "}
              <a
                href="https://github.com/RaghhavMalani/logistics-route-optimization/blob/350b14a4d04e4046489e528bca9c6b9c20a40921/docs/DECISION_POLICY_GATE.md#test-corpus--approved"
                target="_blank"
                rel="noopener noreferrer"
              >
                Original gate and scope →
              </a>
            </p>
          </>
        )}
        {displayed === 5 && (
          <div className="actions">
            <Link className="btn solid" to="/login">
              Open the role demos <span aria-hidden="true">→</span>
            </Link>
            <a
              className="btn ghost"
              href={REPO}
              target="_blank"
              rel="noopener noreferrer"
            >
              Read the code
            </a>
          </div>
        )}
        {HOTSPOTS.some((h) => h.ch === displayed) && (
          <details className="point-index">
            <summary>
              Inspect chapter points (
              {HOTSPOTS.filter((h) => h.ch === displayed).length})
            </summary>
            <dl>
              {HOTSPOTS.filter((h) => h.ch === displayed).map((h) => (
                <div key={h.t}>
                  <dt>{h.t}</dt>
                  <dd>{h.d}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
      </article>
      <footer className="rail">
        <ol aria-label="Voyage chapters">
          {CHAPTERS.map((c, i) => (
            <li key={c.label}>
              <button
                type="button"
                aria-label={`${i}: ${c.label}`}
                aria-current={chapter === i ? "step" : undefined}
                onClick={() => go(i)}
              >
                <span className="track">
                  <span
                    className="fill"
                    ref={(el) => {
                      fills.current[i] = el;
                    }}
                  />
                </span>
                <span className="num-label">
                  0{i} {c.label}
                </span>
              </button>
            </li>
          ))}
        </ol>
        <p className="credit">
          Illustrative composite and simulated movement. Operational evidence is
          separately labelled.
        </p>
      </footer>
    </div>
  );
}
