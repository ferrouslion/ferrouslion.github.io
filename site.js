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

const CHICAGO_DATE = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  month: "short",
  day: "numeric",
  year: "numeric",
});

const RUMBLE_CHANNEL = "https://rumble.com/user/ferrouslion";
const PUBLISHED_AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function formatChicagoDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return CHICAGO_DATE.format(d);
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

function httpsURL(value) {
  if (typeof value !== "string") return null;
  let url;
  try {
    url = new URL(value.trim());
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password) return null;
  return url;
}

function rumbleHttpsURL(value) {
  const url = httpsURL(value);
  if (!url || url.hostname !== "rumble.com") return null;
  return url;
}

function validRumbleItem(item) {
  if (!item || typeof item !== "object") return null;
  const id = typeof item.id === "string" ? item.id.trim() : "";
  const title = typeof item.title === "string" ? item.title.trim() : "";
  if (!id || !title) return null;
  const publishedAt = typeof item.publishedAt === "string" ? item.publishedAt.trim() : "";
  if (!PUBLISHED_AT.test(publishedAt)) return null;
  const published = new Date(publishedAt);
  if (Number.isNaN(published.getTime())) return null;
  const watch = rumbleHttpsURL(item.watchUrl);
  if (!watch) return null;
  const record = {
    id,
    title,
    publishedAt,
    publishedTime: published.getTime(),
    watchUrl: watch.href,
  };
  if (Object.prototype.hasOwnProperty.call(item, "thumbnailUrl") && item.thumbnailUrl != null && item.thumbnailUrl !== "") {
    const thumb = httpsURL(item.thumbnailUrl);
    if (!thumb) return null;
    record.thumbnailUrl = thumb.href;
  }
  if (Object.prototype.hasOwnProperty.call(item, "durationSeconds") && item.durationSeconds != null && item.durationSeconds !== "") {
    const duration = item.durationSeconds;
    if (typeof duration !== "number" || !Number.isFinite(duration) || duration < 0) return null;
    record.durationSeconds = duration;
  }
  return record;
}

function playGlyph() {
  const wrap = document.createElement("span");
  wrap.className = "play";
  wrap.setAttribute("aria-hidden", "true");
  const bubble = document.createElement("span");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "20");
  svg.setAttribute("height", "20");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "currentColor");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M8 5v14l11-7z");
  svg.append(path);
  bubble.append(svg);
  wrap.append(bubble);
  return wrap;
}

function rumbleCard(item) {
  const li = document.createElement("li");
  const link = document.createElement("a");
  link.className = "card video-card hairline hairline-hover rumble-card";
  link.href = item.watchUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const thumb = document.createElement("div");
  thumb.className = "video-thumb";
  if (item.thumbnailUrl) {
    const img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", () => {
      thumb.classList.add("is-fallback");
      img.remove();
    });
    img.src = item.thumbnailUrl;
    thumb.append(img);
  } else {
    thumb.classList.add("is-fallback");
  }
  thumb.append(playGlyph());

  const meta = document.createElement("div");
  meta.className = "video-meta";
  const title = document.createElement("h3");
  title.textContent = item.title;
  const dateP = document.createElement("p");
  const time = document.createElement("time");
  time.dateTime = item.publishedAt;
  time.textContent = formatChicagoDate(item.publishedAt);
  dateP.append(time);
  const action = document.createElement("p");
  action.className = "rumble-watch";
  action.textContent = "Watch on Rumble";
  meta.append(title, dateP, action);

  link.append(thumb, meta);
  li.append(link);
  return li;
}

function rumbleEmpty(channelUrl) {
  const li = document.createElement("li");
  li.className = "card hairline rumble-empty";
  const note = document.createElement("p");
  note.textContent = "No Rumble videos to show yet.";
  const link = document.createElement("a");
  link.href = channelUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Visit Rumble channel";
  li.append(note, link);
  return li;
}

function loadFeaturedRumble() {
  const root = document.getElementById("featured-rumble");
  if (!root) return;
  const dataEl = document.getElementById("featured-rumble-data");
  const channelLink = document.getElementById("rumble-channel-link");
  let channelUrl = RUMBLE_CHANNEL;
  let items = [];
  if (dataEl) {
    try {
      const data = JSON.parse(dataEl.textContent);
      if (data && typeof data === "object" && !Array.isArray(data)) {
        const channel = rumbleHttpsURL(data.channelUrl);
        if (channel) channelUrl = channel.href;
        if (Array.isArray(data.items)) items = data.items.map(validRumbleItem).filter(Boolean);
      }
    } catch {
      items = [];
    }
  }
  if (channelLink) channelLink.href = channelUrl;
  items.sort((a, b) => b.publishedTime - a.publishedTime || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const shown = items.slice(0, 3);
  root.replaceChildren(...(shown.length ? shown.map(rumbleCard) : [rumbleEmpty(channelUrl)]));
}

function chicagoDateKey(now) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

function setupSpecialStream() {
  const slot = document.getElementById("schedule-special");
  if (!slot) return;
  const eventDay = slot.getAttribute("data-date") || "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(eventDay)) return;
  if (chicagoDateKey(new Date()) <= eventDay) slot.hidden = false;
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
      toggle?.setAttribute("aria-expanded", "false");
      toggle?.setAttribute("aria-label", "Open menu");
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
setupSpecialStream();
loadVideos();
loadFeaturedRumble();
loadTwitch();
setupTikTok();
