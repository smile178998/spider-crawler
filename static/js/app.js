/* Modern Web Scraper — Frontend */

let currentResult = null;
let isRunning = false;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const urlInput = $("#url-input");
const scrapeBtn = $("#scrape-btn");
const progressBar = $("#progress-bar");
const statusText = $("#status-text");
const optionsToggle = $("#options-toggle");
const optionsBody = $("#options-body");

// ── Options toggle ────────────────────────────────────────────
optionsToggle.addEventListener("click", () => {
  const open = optionsBody.classList.toggle("open");
  optionsToggle.setAttribute("aria-expanded", open);
});

// ── Tabs ──────────────────────────────────────────────────────
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`#panel-${tab.dataset.tab}`).classList.add("active");
  });
});

// ── Scrape ────────────────────────────────────────────────────
scrapeBtn.addEventListener("click", startScrape);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") startScrape();
});

async function startScrape() {
  const url = urlInput.value.trim();
  if (!url) {
    urlInput.focus();
    return;
  }
  if (isRunning) return;

  isRunning = true;
  setBusy(true);
  clearResults(false);
  appendLog(`▶  Target: ${url}\n\n`);

  const body = {
    url,
    text_selector: $("#text-sel").value.trim(),
    comment_selector: $("#comment-sel").value.trim(),
    cookie: $("#cookie").value.trim(),
    wait_ms: parseInt($("#wait-ms").value, 10) || 2500,
    scroll: $("#scroll").checked,
  };

  try {
    const resp = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          handleEvent(evt);
        } catch (_) { /* skip malformed */ }
      }
    }
  } catch (err) {
    appendLog(`\n❌  ${err.message}\n`, "err");
    setStatus(`❌  ${err.message}`);
  } finally {
    isRunning = false;
    setBusy(false);
  }
}

function handleEvent(evt) {
  const { type, data } = evt;
  if (type === "log") {
    appendLog(data + "\n");
    setStatus(data.slice(-80));
  } else if (type === "done") {
    currentResult = data;
    renderResults(data);
    setStatus("✅  Scrape complete!");
    $("#save-txt").disabled = false;
    $("#save-json").disabled = false;
    appendLog(
      `\n✅ Summary\n` +
      `   Paragraphs : ${data.text_paragraphs.length}\n` +
      `   Comments   : ${data.comments.length}\n` +
      `   Videos     : ${data.videos.length}\n` +
      `   Images     : ${data.images.length}\n` +
      `   Meta tags  : ${Object.keys(data.meta).length}\n`,
      "ok"
    );
    $$(".tab")[0].click();
  } else if (type === "error") {
    appendLog(`\n❌  ${data}\n`, "err");
    setStatus(`❌  ${data}`);
  }
}

// ── Render ────────────────────────────────────────────────────
function renderResults(r) {
  const emptyText = $("#empty-text");
  const textEl = $("#content-text");

  if (r.text_paragraphs.length) {
    emptyText.classList.add("hidden");
    textEl.innerHTML = r.text_paragraphs
      .map((p, i) => `<div class="content-item"><span class="idx">#${i + 1}</span><div>${esc(p)}</div></div>`)
      .join("");
  } else {
    emptyText.classList.remove("hidden");
    textEl.innerHTML = "";
  }
  $("#count-text").textContent = r.text_paragraphs.length;

  $("#content-comments").innerHTML = r.comments.length
    ? r.comments.map((c, i) => `<div class="comment-item"><strong>#${i + 1}</strong> ${esc(c)}</div>`).join("")
    : `<div class="empty-state"><p>No comments found. Try adding a comment selector.</p></div>`;
  $("#count-comments").textContent = r.comments.length;

  $("#content-videos").innerHTML = r.videos.length
    ? r.videos.map((v, i) => `<div class="link-item"><span class="idx">${i + 1}</span><a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a></div>`).join("")
    : `<div class="empty-state"><p>No video links found.</p></div>`;
  $("#count-videos").textContent = r.videos.length;

  $("#content-images").innerHTML = r.images.length
    ? r.images.map((img, i) =>
        `<div class="image-card" onclick="window.open('${esc(img)}','_blank')">
          <img src="${esc(img)}" alt="Image ${i + 1}" loading="lazy" onerror="this.parentElement.style.display='none'" />
          <span class="img-idx">${i + 1}</span>
        </div>`
      ).join("")
    : `<div class="empty-state"><p>No images found.</p></div>`;
  $("#count-images").textContent = r.images.length;

  $("#content-meta").textContent = JSON.stringify(r, null, 2);
}

// ── Export ────────────────────────────────────────────────────
$("#save-json").addEventListener("click", () => {
  if (!currentResult) return;
  download("scrape_result.json", JSON.stringify(currentResult, null, 2), "application/json");
});

$("#save-txt").addEventListener("click", () => {
  if (!currentResult) return;
  const r = currentResult;
  const txt =
    `Title  : ${r.title}\nURL    : ${r.url}\n\n` +
    `===== BODY TEXT =====\n\n${r.text_paragraphs.join("\n\n") || "(none)"}\n\n` +
    `===== COMMENTS =====\n\n${r.comments.join("\n\n") || "(none)"}\n\n` +
    `===== VIDEOS =====\n\n${r.videos.join("\n") || "(none)"}\n\n` +
    `===== IMAGES =====\n\n${r.images.join("\n") || "(none)"}`;
  download("scrape_result.txt", txt, "text/plain");
});

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime + ";charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  setStatus(`Saved → ${filename}`);
}

// ── Clear ─────────────────────────────────────────────────────
$("#clear-btn").addEventListener("click", () => clearResults(true));

function clearResults(confirm) {
  if (confirm && currentResult && !window.confirm("Are you sure you want to clear all results?")) return;
  currentResult = null;
  $("#content-text").innerHTML = "";
  $("#content-comments").innerHTML = "";
  $("#content-videos").innerHTML = "";
  $("#content-images").innerHTML = "";
  $("#content-meta").textContent = "";
  $("#content-log").innerHTML = "";
  $("#empty-text").classList.remove("hidden");
  ["text", "comments", "videos", "images"].forEach((t) => {
    $(`#count-${t}`).textContent = "0";
  });
  $("#save-txt").disabled = true;
  $("#save-json").disabled = true;
  setStatus("Ready");
}

// ── Helpers ───────────────────────────────────────────────────
function setBusy(busy) {
  scrapeBtn.disabled = busy;
  progressBar.classList.toggle("hidden", !busy);
  scrapeBtn.innerHTML = busy
    ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg> Scraping…`
    : `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Start Scrape`;
}

function setStatus(msg) {
  statusText.textContent = msg;
}

function appendLog(text, cls) {
  const log = $("#content-log");
  const span = document.createElement("span");
  if (cls) span.className = `log-${cls}`;
  span.textContent = text;
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// Spin animation for loading icon
const style = document.createElement("style");
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
