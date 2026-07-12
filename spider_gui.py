#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modern Web Scraper — Playwright Edition (Light UI)
====================================================
• Real Chromium browser engine — handles JavaScript, SPAs, lazy loading
• Extracts: body text, comments (heuristic), video links, images, metadata
• Optional CSS selectors for precise extraction on specific sites
• Cookie support to bypass anti-bot protection (521/403 errors)
• Basic stealth: hides common automation fingerprints, randomizes UA/viewport,
  randomizes timing to look less "robotic"
• Export results to TXT or JSON
• Clean, light (white) interface

Dependencies:
  pip install playwright beautifulsoup4 lxml playwright-stealth
  python -m playwright install chromium

Notes on responsible use:
  This tool is meant for scraping content you're authorized to access
  (public pages, your own sites, or sites whose terms permit automated
  access). It does not attempt to defeat CAPTCHAs, paywalls, or
  enterprise-grade bot-mitigation services (Cloudflare/DataDome/etc.).
  Always check a site's robots.txt and terms of service, and keep your
  request rate reasonable.
"""

import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import urlparse

from scraper_core import run_pipeline


# ─────────────────────────────────────────────────────────────────────────────
# GUI — Light / White theme
# ─────────────────────────────────────────────────────────────────────────────

# Palette — modern, sophisticated design with better visual hierarchy
BG        = "#F8FAFC"   # main window background (soft blue-gray)
PANEL     = "#FFFFFF"   # text widget background
CARD      = "#FFFFFF"   # card background
CARD_BD   = "#E2E8F0"   # card border
INPUT_BG  = "#FFFFFF"
INPUT_BD  = "#CBD5E1"
ACCENT    = "#6366F1"   # primary indigo (modern, vibrant)
ACCENT_HV = "#4F46E5"   # hover state
ACCENT_SOFT = "#EEF2FF"
ACCENT_GLOW = "#C7D2FE"
FG        = "#0F172A"   # main text (slate-900)
DIM       = "#64748B"   # secondary text (slate-500)
SUCCESS   = "#10B981"   # emerald green
ERR       = "#EF4444"   # red
WARN      = "#F59E0B"   # amber
SHADOW    = "#64748B"   # shadow color
MONO      = ("JetBrains Mono", 9)
UI        = ("Segoe UI", 10)
BOLD      = ("Segoe UI Semibold", 10)
H1        = ("Segoe UI Semibold", 16)
LABEL_F   = ("Segoe UI", 9)


class ScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Web Scraper — Playwright Edition")
        self.geometry("1160x820")
        self.minsize(940, 660)
        self.configure(bg=BG)

        self._q: queue.Queue = queue.Queue()
        self._result: dict | None = None

        self._style()
        self._build()
        self._poll()

    # ── Theming ────────────────────────────────────────────────────────────
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG,
                    fieldbackground=INPUT_BG, font=UI, bordercolor=INPUT_BD)

        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)

        s.configure("TLabel", background=BG, foreground=FG, font=UI)
        s.configure("Dim.TLabel", background=BG, foreground=DIM, font=LABEL_F)
        s.configure("CardDim.TLabel", background=CARD, foreground=DIM, font=LABEL_F)
        s.configure("H1.TLabel", background=BG, foreground=FG, font=H1)
        s.configure("Sub.TLabel", background=BG, foreground=DIM, font=("Segoe UI", 9))

        # Entries — refined with better focus states
        s.configure("TEntry", fieldbackground=INPUT_BG, foreground=FG,
                    insertcolor=ACCENT, bordercolor=INPUT_BD,
                    lightcolor=INPUT_BD, darkcolor=INPUT_BD, padding=8)
        s.map("TEntry",
              bordercolor=[("focus", ACCENT), ("!focus", INPUT_BD)],
              lightcolor=[("focus", ACCENT_GLOW), ("!focus", INPUT_BD)],
              darkcolor=[("focus", ACCENT), ("!focus", INPUT_BD)],
              fieldbackground=[("focus", "#FFFFFF"), ("!focus", INPUT_BG)])

        # Primary button — modern indigo with better hover states
        s.configure("Primary.TButton", background=ACCENT, foreground="#FFFFFF",
                    font=BOLD, padding=(20, 10), borderwidth=0, relief="flat")
        s.map("Primary.TButton",
              background=[("active", ACCENT_HV), ("pressed", ACCENT_HV), ("disabled", "#A5B4FC")],
              foreground=[("disabled", "#FFFFFF")])

        # Secondary / ghost button — refined with subtle hover
        s.configure("Ghost.TButton", background=CARD, foreground=FG,
                    font=UI, padding=(14, 8), borderwidth=1,
                    bordercolor=CARD_BD, relief="flat")
        s.map("Ghost.TButton",
              background=[("active", "#F1F5F9"), ("pressed", "#E2E8F0")],
              bordercolor=[("active", ACCENT), ("pressed", ACCENT)],
              foreground=[("active", ACCENT), ("pressed", ACCENT_HV)])

        # Tabs — modern design with better selection states
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=DIM,
                    padding=(18, 10), font=UI, borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", BG), ("active", ACCENT_SOFT)],
              foreground=[("selected", ACCENT), ("active", ACCENT_HV)])
        s.layout("TNotebook.Tab", s.layout("TNotebook.Tab"))  # keep default layout

        # Group box (Options card)
        s.configure("TLabelframe", background=BG, bordercolor=CARD_BD, borderwidth=1)
        s.configure("TLabelframe.Label", background=BG, foreground=FG, font=LABEL_F)

        s.configure("TCheckbutton", background=BG, foreground=FG, font=UI)
        s.map("TCheckbutton", 
              background=[("active", BG)],
              foreground=[("active", ACCENT)])

        s.configure("TProgressbar", troughcolor=ACCENT_SOFT, background=ACCENT,
                    borderwidth=0, thickness=6)
        s.configure("TSeparator", background=CARD_BD)

        s.configure("TSpinbox", fieldbackground=INPUT_BG, foreground=FG,
                    background=INPUT_BG, bordercolor=INPUT_BD,
                    arrowcolor=DIM, insertcolor=ACCENT, padding=6)
        s.map("TSpinbox",
              fieldbackground=[("readonly", INPUT_BG), ("focus", INPUT_BG)],
              background=[("active", CARD)],
              bordercolor=[("focus", ACCENT), ("!focus", INPUT_BD)],
              arrowcolor=[("focus", ACCENT), ("!focus", DIM)])

    # ── Layout ─────────────────────────────────────────────────────────────
    def _build(self):
        P = dict(padx=18, pady=6)

        # ── Header ──────────────────────────────────────────────
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=18, pady=(20, 6))

        title_row = ttk.Frame(hdr)
        title_row.pack(fill="x")
        tk.Label(title_row, text="🕷", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 20)).pack(side="left")
        tk.Label(title_row, text="  Modern Web Scraper",
                 bg=BG, fg=FG, font=H1).pack(side="left")
        tk.Label(title_row, text="   Real Chromium browser · handles JS / SPAs / lazy-load",
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))

        ttk.Separator(self).pack(fill="x", padx=18, pady=(12, 12))

        # ── URL input card ──────────────────────────────────────
        url_card = tk.Frame(self, bg=CARD, highlightbackground=CARD_BD,
                             highlightthickness=1, bd=0)
        url_card.pack(fill="x", padx=18, pady=(0, 16))
        inner = tk.Frame(url_card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=14)

        tk.Label(inner, text="Target URL", bg=CARD, fg=DIM,
                 font=LABEL_F).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(inner, textvariable=self.url_var, font=("Segoe UI", 11))
        url_entry.grid(row=1, column=0, sticky="we", padx=(0, 10), ipady=3)
        url_entry.bind("<Return>", lambda e: self._start())

        self.run_btn = ttk.Button(inner, text="▶  Scrape", style="Primary.TButton",
                                   command=self._start)
        self.run_btn.grid(row=1, column=1)
        inner.columnconfigure(0, weight=1)

        # ── Options card ────────────────────────────────────────
        opt_card = tk.Frame(self, bg=CARD, highlightbackground=CARD_BD,
                             highlightthickness=1, bd=0)
        opt_card.pack(fill="x", padx=18, pady=(0, 16))
        opt = tk.Frame(opt_card, bg=CARD)
        opt.pack(fill="x", padx=16, pady=14)

        tk.Label(opt, text="Advanced Options", bg=CARD, fg=DIM,
                 font=LABEL_F).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        # Row 1 — selectors
        tk.Label(opt, text="Text selector (CSS)", bg=CARD, fg=DIM,
                 font=LABEL_F).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self.text_sel_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.text_sel_var,
                  width=28).grid(row=1, column=1, sticky="we", padx=(0, 24), pady=4, ipady=2)

        tk.Label(opt, text="Comment selector (CSS)", bg=CARD, fg=DIM,
                 font=LABEL_F).grid(row=1, column=2, sticky="w", padx=(0, 6), pady=4)
        self.cmt_sel_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.cmt_sel_var,
                  width=28).grid(row=1, column=3, sticky="we", pady=4, ipady=2)

        opt.columnconfigure(1, weight=1)
        opt.columnconfigure(3, weight=1)

        # Row 2 — cookie
        tk.Label(opt, text="Cookie (optional, bypasses anti-bot checks)", bg=CARD, fg=DIM,
                 font=LABEL_F).grid(row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        self.cookie_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.cookie_var,
                  show="•").grid(row=2, column=1, columnspan=3,
                                 sticky="we", pady=4, ipady=2)

        # Row 3 — JS wait + scroll toggle
        wait_row = tk.Frame(opt, bg=CARD)
        wait_row.grid(row=3, column=0, columnspan=4, sticky="we", pady=(12, 0))

        tk.Label(wait_row, text="JS wait (ms)", bg=CARD, fg=DIM,
                 font=LABEL_F).pack(side="left", padx=(0, 8))
        self.wait_var = tk.IntVar(value=2500)
        ttk.Spinbox(wait_row, from_=500, to=12000, increment=500,
                    textvariable=self.wait_var, width=8,
                    style="TSpinbox").pack(side="left", padx=(0, 28))

        self.scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(wait_row, text="Auto-scroll (triggers lazy images/comments)",
                        variable=self.scroll_var).pack(side="left")

        tip_text = ("Tip: leave selectors blank for auto-detection. Increase JS wait for slow "
                     "React/Vue SPAs. Stealth patches (UA/viewport rotation, fingerprint "
                     "hiding) are applied automatically on every run.")
        tk.Label(opt, text=tip_text, bg=CARD, fg=DIM, font=("Segoe UI", 8),
                 wraplength=1000, justify="left").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(12, 0))

        # ── Progress ────────────────────────────────────────────
        self.prog = ttk.Progressbar(self, mode="indeterminate")

        # ── Tabs ────────────────────────────────────────────────
        tabs_wrap = tk.Frame(self, bg=BG, highlightbackground=CARD_BD,
                              highlightthickness=1)
        tabs_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        self.nb = ttk.Notebook(tabs_wrap)
        self.nb.pack(fill="both", expand=True, padx=1, pady=1)

        self.text_box    = self._tab("📄  Body Text")
        self.comment_box = self._tab("💬  Comments")
        self.video_box   = self._tab("🎬  Videos")
        self.image_box   = self._tab("🖼  Images")
        self.meta_box    = self._tab("🏷  Meta / JSON")
        self.log_box     = self._tab("📡  Log")

        # ── Bottom bar ──────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=18, pady=(4, 18))

        for label, cmd in [
            ("💾  Save TXT",  self._save_txt),
            ("💾  Save JSON", self._save_json),
            ("🗑  Clear",     self._clear),
        ]:
            ttk.Button(bar, text=label, style="Ghost.TButton",
                       command=cmd).pack(side="left", padx=(0, 10))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bar, textvariable=self.status_var,
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left", padx=12)

    def _tab(self, label: str) -> scrolledtext.ScrolledText:
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text=label)
        box = scrolledtext.ScrolledText(
            frame, wrap="word", font=MONO,
            bg=PANEL, fg=FG, insertbackground=FG,
            selectbackground=ACCENT_SOFT, selectforeground=FG,
            relief="flat", borderwidth=0, padx=10, pady=8)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.configure(state="disabled")
        return box

    # ── Queue polling ──────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    self._append(self.log_box, payload + "\n")
                    self.status_var.set(payload[-90:])
                elif kind == "done":
                    self._result = payload
                    self._render(payload)
                    self._set_idle("✅  Done!")
                elif kind == "error":
                    self._append(self.log_box, f"\n❌  {payload}\n", ERR)
                    self._set_idle(f"❌  {payload[:90]}")
                    messagebox.showerror("Error", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ── Start ──────────────────────────────────────────────────────────────
    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Enter a URL first.")
            return
        if not urlparse(url).scheme:
            url = "https://" + url
            self.url_var.set(url)

        self._clear(confirm=False)
        self._set_busy("Starting browser …")
        self._append(self.log_box, f"▶  Target: {url}\n\n")

        threading.Thread(
            target=run_pipeline,
            args=(url,
                  self.text_sel_var.get().strip(),
                  self.cmt_sel_var.get().strip(),
                  self.cookie_var.get().strip(),
                  self.wait_var.get(),
                  self.scroll_var.get(),
                  self._q),
            daemon=True,
        ).start()

    # ── Render results ─────────────────────────────────────────────────────
    def _render(self, r: dict):
        lines = [f"Title : {r['title']}", f"URL   : {r['url']}", "=" * 60, ""]
        for i, p in enumerate(r["text_paragraphs"], 1):
            lines.append(f"[{i}]  {p}\n")
        if not r["text_paragraphs"]:
            lines.append("(Nothing found — try adding a Text selector in Options)")
        self._set_text(self.text_box, "\n".join(lines))

        if r["comments"]:
            self._set_text(self.comment_box,
                           "\n\n".join(f"[{i}]  {c}" for i, c in enumerate(r["comments"], 1)))
        else:
            self._set_text(self.comment_box,
                "No comments found.\n\n"
                "Most modern sites load comments via JavaScript after page load.\n"
                "Try: open DevTools → Network → XHR to find the comment API endpoint,\n"
                "or add a Comment selector in Options (e.g. '.comment-body').")

        if r["videos"]:
            self._set_text(self.video_box,
                           "\n".join(f"[{i}]  {v}" for i, v in enumerate(r["videos"], 1)))
        else:
            self._set_text(self.video_box, "(No <video> tags or known embeds found.)")

        if r["images"]:
            self._set_text(self.image_box,
                           "\n".join(f"[{i}]  {v}" for i, v in enumerate(r["images"], 1)))
        else:
            self._set_text(self.image_box, "(No images found.)")

        self._set_text(self.meta_box, json.dumps(r, ensure_ascii=False, indent=2))

        self.nb.select(0)

        self._append(self.log_box,
            f"\n✅ Summary\n"
            f"   Paragraphs : {len(r['text_paragraphs'])}\n"
            f"   Comments   : {len(r['comments'])}\n"
            f"   Videos     : {len(r['videos'])}\n"
            f"   Images     : {len(r['images'])}\n"
            f"   Meta tags  : {len(r['meta'])}\n",
            SUCCESS)

    # ── Save ───────────────────────────────────────────────────────────────
    def _save_json(self):
        if not self._result:
            messagebox.showinfo("Nothing to save", "Run a scrape first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile="scrape_result.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._result, f, ensure_ascii=False, indent=2)
            self.status_var.set(f"Saved → {path}")

    def _save_txt(self):
        if not self._result:
            messagebox.showinfo("Nothing to save", "Run a scrape first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text", "*.txt")],
            initialfile="scrape_result.txt")
        if path:
            r = self._result
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Title  : {r['title']}\nURL    : {r['url']}\n\n")
                f.write("===== BODY TEXT =====\n\n")
                f.write("\n\n".join(r["text_paragraphs"]) or "(none)")
                f.write("\n\n===== COMMENTS =====\n\n")
                f.write("\n\n".join(r["comments"]) or "(none)")
                f.write("\n\n===== VIDEOS =====\n\n")
                f.write("\n".join(r["videos"]) or "(none)")
                f.write("\n\n===== IMAGES =====\n\n")
                f.write("\n".join(r["images"]) or "(none)")
            self.status_var.set(f"Saved → {path}")

    def _clear(self, confirm=True):
        if confirm and not messagebox.askyesno("Clear", "Clear all results?"):
            return
        self._result = None
        for box in (self.text_box, self.comment_box, self.video_box,
                    self.image_box, self.meta_box, self.log_box):
            self._set_text(box, "")
        self.status_var.set("Ready.")

    # ── Helpers ────────────────────────────────────────────────────────────
    def _set_busy(self, msg: str):
        self.run_btn.config(state="disabled")
        self.prog.pack(fill="x", padx=18, pady=(0, 6))
        self.prog.start(10)
        self.status_var.set(msg)

    def _set_idle(self, msg: str):
        self.prog.stop()
        self.prog.pack_forget()
        self.run_btn.config(state="normal")
        self.status_var.set(msg)

    def _append(self, box, text: str, color: str = ""):
        box.configure(state="normal")
        if color:
            tag = f"c{color[1:]}"
            box.tag_configure(tag, foreground=color)
            box.insert("end", text, tag)
        else:
            box.insert("end", text)
        box.see("end")
        box.configure(state="disabled")

    def _set_text(self, box, text: str):
        box.configure(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("1.0", text)
        box.configure(state="disabled")


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()