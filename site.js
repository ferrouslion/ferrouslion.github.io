const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function viewsLabel(views) {
  if (views >= 1_000_000) return (views / 1_000_000).toFixed(1) + "M views";
  if (views >= 1_000) return (views / 1_000).toFixed(1) + "K views";
  if (views === 1) return "1 view";
  return views + " views";
}

function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return MONTHS[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("\u0026", "\u0026amp;")
    .replaceAll("\u003c", "\u0026lt;")
    .replaceAll("\u003e", "\u0026gt;")
    .replaceAll("\u0022", "\u0026quot;");
}

async function loadVideos() {
  const root = document.getElementById("videos");
  if (!root) return;
  try {
    const res = await fetch("./videos.json", { cache: "no-store" });
    if (!res.ok) throw new Error("no feed");
    const videos = await res.json();
    if (!Array.isArray(videos) || videos.length === 0) throw new Error("empty");
    root.innerHTML = videos
      .slice(0, 6)
      .map((v) => cardHtml(v, v.isShort ? "Short" : "", viewsLabel(v.views) + " · " + formatDate(v.published)))
      .join("");
  } catch {
    root.innerHTML = emptyRow("Videos will land here as soon as the feed answers. The full archive lives on YouTube.");
  }
}

function twitchBadge(kind) {
  if (kind === "highlight") return "Highlight";
  if (kind === "upload") return "Upload";
  return "VOD";
}

async function loadTwitch() {
  const root = document.getElementById("twitch-videos");
  if (!root) return;
  try {
    const res = await fetch("./twitch.json", { cache: "no-store" });
    if (!res.ok) throw new Error("no feed");
    const videos = await res.json();
    if (!Array.isArray(videos) || videos.length === 0) throw new Error("empty");
    root.innerHTML = videos
      .slice(0, 3)
      .map((v) => cardHtml(v, twitchBadge(v.kind), formatDate(v.published)))
      .join("");
  } catch {
    root.innerHTML = emptyRow("VODs show up here after a stream. Watch live on Twitch in the meantime.");
  }
}

async function loadRumble() {
  const root = document.getElementById("rumble-videos");
  const fallback = document.getElementById("rumble-fallback");
  if (!root) return;
  try {
    const res = await fetch("./rumble.json", { cache: "no-store" });
    if (!res.ok) throw new Error("no feed");
    const videos = await res.json();
    if (!Array.isArray(videos) || videos.length === 0) throw new Error("empty");
    root.innerHTML = videos
      .slice(0, 3)
      .map((v) => cardHtml(v, "Rumble", formatDate(v.published)))
      .join("");
    if (fallback) fallback.hidden = true;
  } catch {
    root.innerHTML = "";
    if (fallback) fallback.hidden = false;
  }
}

function cardHtml(v, badge, meta) {
  const tag = badge ? `<span class="tag">${escapeHtml(badge)}</span>` : "";
  return `<li>
          <a class="card video-card hairline hairline-hover" href="${escapeHtml(v.url)}" target="_blank" rel="noreferrer">
            <div class="video-thumb">
              <img src="${escapeHtml(v.thumbnail || "")}" alt="">
              <span class="play"><span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
              </span></span>
              ${tag}
            </div>
            <div class="video-meta">
              <h3>${escapeHtml(v.title)}</h3>
              <p>${escapeHtml(meta)}</p>
            </div>
          </a>
        </li>`;
}

function emptyRow(text) {
  return `<li class="card hairline" style="grid-column:1/-1;padding:2.5rem;text-align:center;color:var(--muted);font-size:.875rem">${escapeHtml(text)}</li>`;
}

function setupHeader() {
  const header = document.querySelector(".header");
  const toggle = document.querySelector(".menu-btn");
  const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 12);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
  toggle?.addEventListener("click", () => {
    const open = header.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    document.body.style.overflow = open ? "hidden" : "";
  });
  header.querySelectorAll(".nav-mobile a").forEach((a) => {
    a.addEventListener("click", () => {
      header.classList.remove("is-open");
      document.body.style.overflow = "";
    });
  });
}

function setupTikTok() {
  const host = document.getElementById("tiktok-embed");
  if (!host) return;
  const script = document.createElement("script");
  script.src = "https://www.tiktok.com/embed.js";
  script.async = true;
  document.body.appendChild(script);
}

setupHeader();
loadVideos();
loadRumble();
loadTwitch();
setupTikTok();
