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
      .map((v) => {
        const short = v.isShort ? " is-short" : "";
        const tag = v.isShort ? `<span class="tag">Short</span>` : "";
        return `<li>
          <a class="card video-card hairline hairline-hover${short}" href="${escapeHtml(v.url)}" target="_blank" rel="noreferrer">
            <div class="video-thumb">
              <img src="${escapeHtml(v.thumbnail)}" alt="">
              <span class="play"><span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
              </span></span>
              ${tag}
            </div>
            <div class="video-meta">
              <h3>${escapeHtml(v.title)}</h3>
              <p>${viewsLabel(v.views)} · ${formatDate(v.published)}</p>
            </div>
          </a>
        </li>`;
      })
      .join("");
  } catch {
    root.innerHTML = `<li class="card hairline" style="grid-column:1/-1;padding:2.5rem;text-align:center;color:var(--muted);font-size:.875rem">
      Videos will land here as soon as the feed answers. The full archive lives on YouTube.
    </li>`;
  }
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
setupTikTok();
