#!/usr/bin/env python3
"""Record a usage demo GIF for the README."""

import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1:8000"
OUTPUT = BASE_DIR / "demo.gif"
FRAMES_DIR = BASE_DIR / ".demo_frames"

VIEWPORT = {"width": 1280, "height": 900}
GIF_WIDTH = 1000
FRAME_MS = 1400


def capture(page, name: str, frames: list[Path]) -> None:
    path = FRAMES_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    frames.append(path)
    print(f"  captured {name}")


def to_gif_frame(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    ratio = GIF_WIDTH / img.width
    height = max(1, int(img.height * ratio))
    img = img.resize((GIF_WIDTH, height), Image.Resampling.LANCZOS)
    return img.quantize(colors=128, method=Image.Quantize.MEDIANCUT)


def main() -> None:
    if FRAMES_DIR.exists():
        for f in FRAMES_DIR.glob("*.png"):
            f.unlink()
    FRAMES_DIR.mkdir(exist_ok=True)

    ordered: list[Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()

        print("[demo] Opening web UI ...")
        page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(1.2)
        capture(page, "01_home", ordered)

        page.fill("#url-input", "https://example.com")
        time.sleep(0.6)
        capture(page, "02_url_filled", ordered)

        page.click("#options-toggle")
        time.sleep(0.9)
        capture(page, "03_advanced_options", ordered)

        page.click("#scrape-btn")
        time.sleep(1.0)
        capture(page, "04_scraping_started", ordered)

        print("[demo] Waiting for scrape to finish ...")
        done = False
        for i in range(45):
            status = page.locator("#status-text").inner_text(timeout=2000)
            if "complete" in status.lower():
                done = True
                break
            if i in (2, 5):
                capture(page, f"05_in_progress_{i}", ordered)
            time.sleep(2)

        if not done:
            print("[demo] Warning: scrape may not have finished; capturing current state.")

        time.sleep(0.8)
        page.click('.tab[data-tab="text"]')
        time.sleep(0.5)
        capture(page, "06_results_text", ordered)

        page.click('.tab[data-tab="log"]')
        time.sleep(0.7)
        capture(page, "07_log", ordered)

        if page.locator('.tab[data-tab="selectors"]').count():
            page.click('.tab[data-tab="selectors"]')
            time.sleep(0.7)
            capture(page, "08_selectors", ordered)

        browser.close()

    key_order = [
        "01_home",
        "02_url_filled",
        "03_advanced_options",
        "04_scraping_started",
        "05_in_progress_2",
        "06_results_text",
        "07_log",
        "08_selectors",
    ]
    frames = []
    for key in key_order:
        path = FRAMES_DIR / f"{key}.png"
        if path.exists():
            frames.append(to_gif_frame(path))

    if len(frames) < 3:
        frames = [to_gif_frame(p) for p in ordered]

    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
    )
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"[demo] Saved {OUTPUT} ({size_kb:.0f} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
