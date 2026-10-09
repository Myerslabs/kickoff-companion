// Pixel pictures for the newspaper (Phase 17 #26, owner pick A, 2026-10-07): each story gets a tiny retro picture
// chosen by its topic and drawn in the team's colors, varied a little by the story's own title, so two stories never
// look the same; a story that names one of our players or the opponent's shows that player's headshot, crunched into
// the same pixels. Drawn on a 40 by 24 canvas and scaled up with crisp pixels; nothing is downloaded but our own
// headshot cache. The picture is always smaller than its headline (the story is the star).
//
//   pixelPicture({ topic, seed, playerId, colors, label })  -> <canvas class="px-pic">
//   seedOf(text)        a stable number from a string (the same title, the same picture)
//   TOPICS              the topics drawn: game, injury, recruiting, coach, weather, nfl, other-sport, practice, trophy, rankings, stadium, scoreboard

const W = 40;
const H = 24;
export const TOPICS = ["game", "injury", "recruiting", "coach", "weather", "nfl", "other-sport", "practice", "trophy", "rankings", "stadium", "scoreboard"];

export function seedOf(value) {
  const s = String(value ?? "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h || 1;
}

function rng(seed) {
  let s = seed % 233280 || 1;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

/** The colors in play: ours, our accent, the opponent's, from the page's own tokens (the theme painted them). */
function themeColors() {
  const read = (name, fallback) => {
    try {
      const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch {
      return fallback;
    }
  };
  return { us: read("--team-us", "#3D6BFF"), accent: read("--team-accent", "#FA4616"), them: read("--opp", "#9AA1AE") };
}

const SKY = "#1B2433";
const FIELD = "#2E7D32";
const FIELD2 = "#388E3C";
const CHALK = "#F2F2F2";
const GOLD = "#FFD166";
const GREY = "#5A606B";

const DRAW = {
  game(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, 9, SKY);
    for (let i = 0; i < 40; i += 1) rect(Math.floor(r() * W), Math.floor(r() * 7), 1, 1, r() > 0.5 ? c.accent : c.us);
    rect(0, 9, W, 15, FIELD);
    for (let x = 3; x < W; x += 6) rect(x, 9, 1, 15, FIELD2);
    for (let x = 5; x < W; x += 12) rect(x, 9, 1, 15, CHALK);
    for (let i = 0; i < 5; i += 1) { const x = 6 + Math.floor(r() * 12); const y = 12 + Math.floor(r() * 9); rect(x, y, 2, 3, c.us); rect(x, y - 1, 2, 1, c.accent); }
    for (let i = 0; i < 5; i += 1) { const x = 22 + Math.floor(r() * 12); const y = 12 + Math.floor(r() * 9); rect(x, y, 2, 3, c.them); rect(x, y - 1, 2, 1, CHALK); }
    rect(19, 15, 2, 1, "#8B5A2B");
  },
  nfl(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, SKY);
    g.fillStyle = c.us;
    g.beginPath();
    g.arc(19, 14, 9, Math.PI, 0);
    g.lineTo(28, 20);
    g.lineTo(12, 20);
    g.fill();
    rect(11, 13, 18, 2, c.accent);
    rect(26, 15, 6, 1, GREY);
    rect(26, 17, 6, 1, GREY);
    rect(31, 14, 1, 5, GREY);
    for (let i = 0; i < 12; i += 1) rect(Math.floor(r() * W), Math.floor(r() * 5), 1, 1, GOLD);
  },
  recruiting(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#20243A");
    g.fillStyle = GOLD;
    g.beginPath();
    const cx = 17 + Math.floor(r() * 6);
    for (let i = 0; i < 10; i += 1) { const a = -Math.PI / 2 + (i * Math.PI) / 5; const rr = i % 2 ? 3.5 : 9; g.lineTo(cx + rr * Math.cos(a), 12 + rr * Math.sin(a)); }
    g.fill();
    for (let i = 0; i < 18; i += 1) rect(Math.floor(r() * W), Math.floor(r() * H), 1, 1, r() > 0.5 ? CHALK : c.accent);
  },
  injury(g, r) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#25303A");
    const x = 12 + Math.floor(r() * 4);
    rect(x, 4, 12, 16, CHALK);
    rect(x + 4, 7, 4, 10, "#D32F2F");
    rect(x + 1, 10, 10, 4, "#D32F2F");
    for (let i = 0; i < W; i += 4) rect(i, 22, 2, 2, GREY);
  },
  coach(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#1E2633");
    g.fillStyle = r() > 0.5 ? "#C68E5A" : "#8D5B3A";
    g.beginPath();
    g.arc(20, 12, 6, 0, Math.PI * 2);
    g.fill();
    rect(13, 16, 14, 8, c.us);
    rect(13, 6, 14, 3, c.accent);
    rect(12, 9, 2, 6, "#222");
    rect(26, 9, 2, 6, "#222");
    rect(13, 8, 14, 1, "#222");
    rect(27, 14, 4, 1, "#222");
    rect(30, 13, 2, 2, "#444");
  },
  weather(g, r) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#1A2230");
    g.fillStyle = "#7D8794";
    for (const [x, y, rr] of [[14, 8, 6], [21, 7, 7], [27, 9, 5]]) { g.beginPath(); g.arc(x, y, rr, 0, Math.PI * 2); g.fill(); }
    g.fillStyle = GOLD;
    g.beginPath();
    g.moveTo(20, 12); g.lineTo(16, 19); g.lineTo(20, 18); g.lineTo(17, 24); g.lineTo(25, 15); g.lineTo(21, 16);
    g.fill();
    for (let i = 0; i < 14; i += 1) rect(Math.floor(r() * W), 14 + Math.floor(r() * 10), 1, 2, "#5DA9E9");
  },
  "other-sport"(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#2A2118");
    for (let x = 0; x < W; x += 5) rect(x, 18, 3, 6, "#8B6A3E");
    g.fillStyle = "#E07B2A";
    g.beginPath();
    g.arc(20, 10, 7, 0, Math.PI * 2);
    g.fill();
    rect(13, 10, 14, 1, "#3A2410");
    rect(20, 3, 1, 14, "#3A2410");
    for (let i = 0; i < 8; i += 1) rect(Math.floor(r() * W), Math.floor(r() * 4), 1, 1, c.accent);
  },
  practice(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, 8, SKY);
    rect(0, 8, W, 16, FIELD);
    for (let x = 4; x < W; x += 9) rect(x, 8, 1, 16, FIELD2);
    for (let i = 0; i < 4; i += 1) { const x = 5 + i * 8 + Math.floor(r() * 3); rect(x, 17, 3, 1, "#FF7A00"); rect(x + 1, 16, 1, 1, "#FF7A00"); }
    rect(27, 11, 5, 10, c.us);
    rect(28, 9, 3, 3, "#C68E5A");
    rect(33, 12, 2, 8, GREY);
    rect(32, 20, 4, 1, GREY);
  },
  trophy(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#1F2433");
    rect(14, 4, 12, 8, GOLD);
    rect(12, 5, 2, 4, GOLD);
    rect(26, 5, 2, 4, GOLD);
    rect(17, 12, 6, 4, GOLD);
    rect(18, 16, 4, 3, GOLD);
    rect(13, 19, 14, 3, c.accent);
    rect(15, 6, 2, 4, "#FFF2B8");
    for (let i = 0; i < 14; i += 1) rect(Math.floor(r() * W), Math.floor(r() * 4), 1, 1, r() > 0.5 ? c.us : CHALK);
  },
  rankings(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#1B2230");
    rect(8, 14, 8, 8, GREY);
    rect(16, 8, 8, 14, GOLD);
    rect(24, 16, 8, 6, "#8D6E63");
    rect(19, 4, 2, 4, CHALK);
    rect(18, 5, 4, 1, CHALK);
    rect(11, 10, 2, 4, CHALK);
    rect(27, 12, 2, 4, CHALK);
    for (let i = 0; i < 10; i += 1) rect(Math.floor(r() * W), Math.floor(r() * 3), 1, 1, c.accent);
  },
  stadium(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, 10, SKY);
    rect(0, 10, W, 14, "#3A3F4B");
    for (let x = 1; x < W; x += 3) rect(x, 11 + (x % 2), 2, 2, r() > 0.5 ? c.us : c.accent);
    rect(0, 17, W, 7, FIELD);
    for (const x of [3, 33]) { rect(x, 2, 1, 9, GREY); rect(x - 1, 1, 4, 2, GOLD); }
    rect(6, 20, 28, 1, CHALK);
  },
  scoreboard(g, r, c) {
    const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
    rect(0, 0, W, H, "#10141C");
    rect(6, 4, 28, 14, "#222A38");
    rect(8, 6, 11, 10, "#0B0F16");
    rect(21, 6, 11, 10, "#0B0F16");
    for (const x of [10, 13, 16]) rect(x, 8 + (x % 2), 2, 5, c.accent);
    for (const x of [23, 26, 29]) rect(x, 8 + ((x + 1) % 2), 2, 5, GOLD);
    rect(18, 19, 4, 4, GREY);
    rect(10, 22, 20, 2, GREY);
  },
};

/** The masthead's banner: a stadium skyline in the team's colors, wider than a story picture and drawn the same way (Phase 19). */
export function pixelBanner({ seed = 1, colors = null } = {}) {
  const w = 160;
  const h = 18;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.className = "px-pic px-pic--banner";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "A pixel stadium skyline");
  const g = typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  if (!g) return canvas;
  const c = colors && typeof colors === "object" ? { ...themeColors(), ...colors } : themeColors();
  const r = rng(seed);
  const rect = (x, y, rw, rh, col) => { g.fillStyle = col; g.fillRect(x, y, rw, rh); };
  try {
    rect(0, 0, w, h, SKY);
    for (let i = 0; i < 30; i += 1) rect(Math.floor(r() * w), Math.floor(r() * 7), 1, 1, r() > 0.5 ? c.accent : CHALK);
    rect(20, 8, 120, 8, "#3A3F4B");
    for (let x = 22; x < 138; x += 3) rect(x, 9 + (x % 2), 2, 2, r() > 0.5 ? c.us : c.accent);
    rect(0, 14, w, 4, FIELD);
    for (const x of [14, 144]) { rect(x, 1, 1, 14, GREY); rect(x - 2, 0, 5, 2, GOLD); }
    rect(40, 16, 80, 1, CHALK);
  } catch (error) {
    console.warn("The masthead banner could not be drawn.", error);
  }
  return canvas;
}

/** A headshot crunched into the picture's pixels; false when it cannot be read (the topic picture stays). */
function drawHeadshot(g, img, colors) {
  try {
    g.fillStyle = colors.us;
    g.fillRect(0, 0, W, H);
    const scale = H / img.naturalHeight;
    const width = img.naturalWidth * scale;
    g.imageSmoothingEnabled = true;
    g.drawImage(img, (W - width) / 2, 0, width, H);
    return true;
  } catch {
    return false;
  }
}

export function pixelPicture({ topic = "game", seed = 1, playerId = null, colors = null, label = "" } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  canvas.className = "px-pic";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", typeof label === "string" && label ? label : "A pixel picture for the story");
  const g = typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  if (!g) return canvas; // no drawing surface (tests): an empty picture keeps its place
  const c = colors && typeof colors === "object" ? { ...themeColors(), ...colors } : themeColors();
  const kind = TOPICS.includes(topic) ? topic : "game";
  try {
    DRAW[kind](g, rng(seed), c);
  } catch (error) {
    console.warn("A pixel picture could not be drawn; the story shows without it.", error);
  }
  const id = typeof playerId === "string" && /^\d{1,12}$/.test(playerId) ? playerId : null;
  if (id && typeof Image === "function") {
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && drawHeadshot(g, img, c)) canvas.classList.add("px-pic--face");
    };
    img.onerror = () => {}; // no headshot: the topic picture stays
    img.src = `/media/headshot/${id}`;
  }
  return canvas;
}
