"""Browser smoke test and screenshot capture for the terminal.

Drives every screen at the three viewport sizes an operations desk actually
uses, records any console error or failed request, checks for horizontal
overflow and captures a screenshot per screen per size. It is the standing
answer to "did anyone actually look at the UI?".

    python scripts/ui_smoke.py --base-url http://localhost:5174 \
        --out work/ui-screens

Exit code is non-zero when a screen fails to render, logs a console error or
overflows horizontally, so it can gate a release.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

VIEWPORTS = [
    ("1920x1080", 1920, 1080),
    ("1440x900", 1440, 900),
    ("1366x768", 1366, 768),
]

SCREENS = [
    ("radar", "/"),
    ("port", "/port?port=INNSA"),
    ("model", "/model?port=INNSA"),
    ("sim", "/sim?scenario=HORMUZ&intensity=1"),
    ("fleet", "/fleet"),
    ("wx", "/wx?port=INMUN"),
    ("sar", "/sar?port=INMAA"),
    ("nlp", "/nlp?entity=ALL"),
]

#: Text that means the screen rendered an error rather than content.
FAILURE_MARKERS = ["Intelligence API unavailable", "Something went wrong"]

#: Console noise that is not a product defect. The hydration warning comes from
#: the dev-only source-location tagger, whose data-tsd-source line numbers
#: differ between the SSR and client bundles; it does not occur in a production
#: build, which is why this script should also be run against `vite preview`.
IGNORED_CONSOLE = (
    "favicon",
    "hmr",
    "data-tsd-source",
    "a tree hydrated but some attributes",
)


@dataclass
class ScreenResult:
    screen: str
    viewport: str
    ok: bool = True
    console_errors: list = field(default_factory=list)
    failed_requests: list = field(default_factory=list)
    horizontal_overflow: int = 0
    notes: list = field(default_factory=list)
    screenshot: str = ""

    def to_dict(self) -> dict:
        return {
            "screen": self.screen,
            "viewport": self.viewport,
            "ok": self.ok,
            "consoleErrors": self.console_errors,
            "failedRequests": self.failed_requests,
            "horizontalOverflowPx": self.horizontal_overflow,
            "notes": self.notes,
            "screenshot": self.screenshot,
        }


def run(base_url: str, out_dir: Path, headless: bool = True) -> list[ScreenResult]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[ScreenResult] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        for label, width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            for screen, path in SCREENS:
                result = ScreenResult(screen=screen, viewport=label)
                console_errors: list[str] = []
                failed: list[str] = []

                page.on("console", lambda msg, sink=console_errors:
                        sink.append(msg.text) if msg.type == "error" else None)
                page.on("requestfailed", lambda request, sink=failed:
                        sink.append(f"{request.method} {request.url}"))

                try:
                    page.goto(f"{base_url}{path}", wait_until="networkidle",
                              timeout=45_000)
                    page.wait_for_timeout(1_200)
                except Exception as exc:
                    result.ok = False
                    result.notes.append(f"navigation failed: {exc}")

                if result.ok:
                    body = page.inner_text("body")
                    for marker in FAILURE_MARKERS:
                        if marker in body:
                            result.ok = False
                            result.notes.append(f"screen rendered '{marker}'")
                    if len(body.strip()) < 200:
                        result.ok = False
                        result.notes.append("screen rendered almost no text")

                    overflow = page.evaluate(
                        "() => Math.max(0, document.documentElement.scrollWidth"
                        " - document.documentElement.clientWidth)")
                    result.horizontal_overflow = int(overflow)
                    if overflow > 4:
                        result.ok = False
                        result.notes.append(f"horizontal overflow {overflow}px")

                shot = out_dir / f"{screen}-{label}.png"
                try:
                    page.screenshot(path=str(shot))
                    result.screenshot = str(shot)
                except Exception as exc:  # pragma: no cover
                    result.notes.append(f"screenshot failed: {exc}")

                # Only fail on errors that matter; a missing favicon or a
                # dev-server HMR notice is not a product defect.
                result.console_errors = [
                    error for error in console_errors
                    if not any(token in error.lower() for token in IGNORED_CONSOLE)
                ]
                result.failed_requests = [
                    request for request in failed if "favicon" not in request.lower()
                ]
                if result.console_errors:
                    result.ok = False
                    result.notes.append("console errors present")

                results.append(result)
                status = "OK " if result.ok else "FAIL"
                print(f"[{status}] {label:>9} {screen:<6} "
                      f"overflow={result.horizontal_overflow}px "
                      f"errors={len(result.console_errors)}")

            context.close()
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminal UI smoke test.")
    parser.add_argument("--base-url", default="http://localhost:5174")
    parser.add_argument("--out", default="work/ui-screens")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    results = run(args.base_url, out_dir, headless=not args.headed)

    report = out_dir / "ui_smoke_report.json"
    report.write_text(
        json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    print(f"\nReport: {report}")

    failures = [r for r in results if not r.ok]
    if failures:
        print(f"\n{len(failures)} screen/viewport combinations failed:")
        for failure in failures:
            print(f"  {failure.viewport} {failure.screen}: "
                  f"{'; '.join(failure.notes) or 'unknown'}")
            for error in failure.console_errors[:3]:
                print(f"      console: {error[:200]}")
        return 1
    print("\nAll screens rendered cleanly at every viewport.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
