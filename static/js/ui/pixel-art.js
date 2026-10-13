// Pixel pictures for the newspaper (Phase 17 #26, owner pick A, 2026-10-07): each story gets a tiny retro picture
// chosen by its topic and drawn in the team's colors, varied a little by the story's own title, so two stories never
// look the same; a story that names one of our players or the opponent's shows that player's headshot, crunched into
// the same pixels. Drawn on a 40 by 24 canvas and scaled up with crisp pixels; nothing is downloaded but our own
// headshot cache. The picture is always smaller than its headline (the story is the star).
//
//   pixelPicture({ topic, seed, playerId, colors, label })  -> <canvas class="px-pic">
//   seedOf(text)        a stable number from a string (the same title, the same picture)
//   TOPICS              the topics drawn: game, injury, recruiting, coach, weather, nfl, other-sport, practice, trophy, rankings, stadium, scoreboard
//
// Queue items 10 to 12 (mocks approved 2026-10-13): pictures that fill the box they sit in, drawn on a grid shaped like
// the box (so nothing is cut or stretched) with the same palette and crisp pixels, redrawn when the box changes size.
//   fillPicture(kind, opts, label)  -> <canvas class="px-pic px-fill px-fill--<kind>">
//       helmet   a retro helmet in a team's colors facing the other team ({ color, alt, flip, seed })
//       stadium  the lead story's stadium under the lights in our colors ({ seed })
//       coach    the made-up coach (owner: "make one up"): visor, headset, play sheet, our colors
//       player   a player's headshot crunched into the pixels ({ playerId }); without one, a stand-in in our colors
//                wearing his number ({ number })
//   refitPictures(root)  redraws every fill picture under root at its box's size (after a layout or a resize)

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

// --- pictures that fill their box (items 10 to 12) -----------------------------------------------------------------

const hex6 = (c) => {
  const m = String(c ?? "").trim().match(/^#?([0-9a-f]{6})$/i);
  return m ? `#${m[1]}` : null;
};

/** Blend two colors: t = 0 is a, 1 is b. */
function mix(a, b, t) {
  const x = hex6(a) || "#888888";
  const y = hex6(b) || "#000000";
  const ch = (s, i) => parseInt(s.slice(1 + i * 2, 3 + i * 2), 16);
  return `#${[0, 1, 2].map((i) => Math.round(ch(x, i) * (1 - t) + ch(y, i) * t).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(c) {
  const h = hex6(c) || "#888888";
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// a 3 by 5 pixel font for the digits (a stand-in player's number)
const DIGITS = { 0: ["111", "101", "101", "101", "111"], 1: ["010", "110", "010", "010", "111"], 2: ["111", "001", "111", "100", "111"], 3: ["111", "001", "111", "001", "111"], 4: ["101", "101", "111", "001", "001"], 5: ["111", "100", "111", "001", "111"], 6: ["111", "100", "111", "101", "111"], 7: ["111", "001", "010", "010", "010"], 8: ["111", "101", "111", "101", "111"], 9: ["111", "101", "111", "001", "111"] };

function digits(g, value, x, y, color) {
  let cx = x;
  g.fillStyle = color;
  for (const ch of String(value)) {
    const rows = DIGITS[ch];
    if (!rows) {
      cx += 2;
      continue;
    }
    rows.forEach((row, ry) => [...row].forEach((bit, rx) => {
      if (bit === "1") g.fillRect(cx + rx, y + ry, 1, 1);
    }));
    cx += 4;
  }
}

/** The helmet facing right as a 31 by 24 pixel map (colors or null). */
function helmetMap(color, alt) {
  const MW = 31;
  const MH = 24;
  const shell = hex6(color) || "#7A7F8A";
  let stripe = hex6(alt) || CHALK;
  if (Math.abs(luminance(stripe) - luminance(shell)) < 0.08) stripe = luminance(shell) > 0.4 ? "#1A1D24" : CHALK; // a stripe that shows
  const light = mix(shell, "#ffffff", 0.32);
  const dark = mix(shell, "#000000", 0.32);
  const OUT = "#0B0E14";
  const MASK = "#D8DDE5";
  const MASKD = "#8D96A3";
  const PAD = "#2A2F38";
  const map = Array.from({ length: MH }, () => Array(MW).fill(null));
  const cx = 13;
  const cy = 12;
  const r2 = (x, y) => ((x + 0.5 - cx) / 12.4) ** 2 + ((y + 0.5 - cy) / 11.2) ** 2;
  const cheek = (y) => 18 + Math.floor((y - 10) * 0.45); // the cheek guard slopes forward toward the chin
  const inShell = (x, y) => {
    if (r2(x, y) > 1 && !(y >= 10 && y <= 19 && x <= cheek(y) && x >= 17)) return false;
    if (y >= 10 && x > cheek(y)) return false; // the face opening
    return y <= 20.5 - (x / 21) * 2.5; // the lower edge rises a little from the neck to the chin
  };
  for (let y = 10; y <= 18; y += 1) for (let x = 17; x <= 26; x += 1) if (x > cheek(y) && r2(x, y) <= 1.5) map[y][x] = PAD; // the inside, seen through the mask
  for (let y = 0; y < MH; y += 1) {
    for (let x = 0; x < MW; x += 1) {
      if (!inShell(x, y)) continue;
      const r = Math.sqrt(r2(x, y));
      let c = shell;
      if (y > cy + 4 || (x < cx - 7 && y > cy + 1)) c = dark;
      if (r < 0.62 && x < cx - 1 && y < cy - 1) c = light;
      if (r > 0.74 && r <= 0.9 && y < cy - 2 && x > 2 && x < 23) c = stripe; // the stripe follows the crown
      map[y][x] = c;
    }
  }
  for (let y = 0; y < MH; y += 1) {
    for (let x = 0; x < MW; x += 1) {
      const d = Math.hypot(x + 0.5 - (cx + 1.5), y + 0.5 - (cy + 2.5)); // the ear hole and its snap
      if (map[y][x] && map[y][x] !== PAD && d <= 1.3) map[y][x] = "#0F1218";
      else if (map[y][x] && map[y][x] !== PAD && d <= 2.3) map[y][x] = mix(shell, "#000000", 0.5);
    }
  }
  const filled = (x, y) => x >= 0 && y >= 0 && x < MW && y < MH && map[y][x] !== null;
  const edge = [];
  for (let y = 0; y < MH; y += 1) for (let x = 0; x < MW; x += 1) if (!filled(x, y) && (filled(x - 1, y) || filled(x + 1, y) || filled(x, y - 1) || filled(x, y + 1))) edge.push([x, y]);
  for (const [x, y] of edge) map[y][x] = OUT;
  const put = (x, y, c) => {
    if (x >= 0 && y >= 0 && x < MW && y < MH) map[y][x] = c;
  };
  const bar = (x0, x1, y) => {
    for (let x = x0; x <= x1; x += 1) put(x, y, MASK);
  };
  bar(cheek(11), 27, 11); // the face mask: two bars, a bowed upright, a chin bar
  bar(cheek(15), 28, 15);
  for (let y = 11; y <= 18; y += 1) put(y <= 12 || y >= 18 ? 27 : 28, y, MASK);
  put(28, 12, MASKD);
  put(28, 17, MASKD);
  bar(cheek(18) + 1, 27, 18);
  for (const y of [12, 16]) for (let x = cheek(y) + 1; x <= 26; x += 1) if (map[y][x] === PAD) map[y][x] = MASKD;
  for (let y = 9; y <= 20; y += 1) {
    for (let x = 19; x <= 30; x += 1) {
      if (map[y][x] === null && (map[y][x - 1] === MASK || map[y][x - 1] === MASKD || map[y - 1]?.[x] === MASK || map[y + 1]?.[x] === MASK)) map[y][x] = OUT;
    }
  }
  for (const x of [16, 17, 18, 19, 20, 21]) if (map[19][x] === null || map[19][x] === OUT) map[19][x] = "#2E323A"; // the chin strap
  return map;
}

function paintMap(g, map, x0, y0, flip) {
  const MW = map[0].length;
  map.forEach((row, y) => row.forEach((c, x) => {
    if (c) {
      g.fillStyle = c;
      g.fillRect(x0 + (flip ? MW - 1 - x : x), y0 + y, 1, 1);
    }
  }));
}

function rectOn(g) {
  return (x, y, rw, rh, col) => {
    g.fillStyle = col;
    g.fillRect(Math.round(x), Math.round(y), Math.round(rw), Math.round(rh));
  };
}

const FILL = {
  // a helmet on the turf under the lights, facing the other team's
  helmet(g, w, h, r, o) {
    const rect = rectOn(g);
    rect(0, 0, w, h, SKY);
    for (let i = 0; i < Math.round((w * h) / 40); i += 1) rect(Math.floor(r() * w), Math.floor(r() * (h - 9)), 1, 1, r() > 0.5 ? mix(o.color, "#ffffff", 0.3) : "#3A4560");
    const map = helmetMap(o.color, o.alt);
    const mw = map[0].length;
    const mh = map.length;
    const turf = h - 5;
    const cx = w / 2;
    const cy = turf - mh / 2;
    for (let y = 0; y < turf; y += 1) {
      for (let x = 0; x < w; x += 1) {
        const d = ((x - cx) / (mw * 0.8)) ** 2 + ((y - cy) / (mh * 0.75)) ** 2; // a spotlight behind it
        if (d < 1) rect(x, y, 1, 1, d < 0.55 ? "#2B3650" : "#243048");
      }
    }
    rect(0, turf, w, h - turf, FIELD);
    for (let x = o.flip ? 1 : 3; x < w; x += 6) rect(x, turf, 2, h - turf, FIELD2);
    rect(0, turf, w, 1, CHALK);
    const x0 = Math.round((w - mw) / 2);
    for (let x = x0 + 3; x < x0 + mw - 4; x += 1) rect(x, turf + 1, 1, 1, "#1E5A23"); // its shadow
    paintMap(g, map, x0, turf - mh + 2, o.flip);
  },
  // the lead's stadium: the night sky and its towers, the stands in our colors, a scoreboard, the turf
  stadium(g, w, h, r, o) {
    const rect = rectOn(g);
    const sky = Math.round(h * 0.44);
    const stands = Math.round(h * 0.73);
    rect(0, 0, w, sky, SKY);
    for (let i = 0; i < Math.round((w * sky) / 18); i += 1) rect(Math.floor(r() * w), Math.floor(r() * (sky - 2)), 1, 1, r() > 0.5 ? o.accent : o.us);
    rect(0, sky, w, stands - sky, "#3A3F4B");
    for (let y = sky + 1; y < stands - 1; y += 2) for (let x = y % 4 === 1 ? 0 : 1; x < w; x += 2) rect(x, y, 1, 1, r() > 0.5 ? o.us : o.accent);
    rect(0, stands - 1, w, 1, "#262A33");
    rect(0, stands, w, h - stands, FIELD);
    for (let y = stands + 2; y < h; y += 4) rect(0, y, w, 2, FIELD2);
    rect(0, stands, w, 1, CHALK);
    for (const x of w >= 18 ? [Math.round(w * 0.14), Math.round(w * 0.86) - 1] : [Math.round(w / 2)]) {
      rect(x, 3, 1, stands - 3, GREY);
      rect(x - 2, 1, 5, 3, GOLD);
      rect(x - 2, 2, 5, 1, "#FFF2B8");
      for (const dx of [-3, 3]) rect(x + dx, 2, 1, 1, "#B89A4A");
    }
    if (w >= 22) {
      const bw = Math.min(14, Math.round(w * 0.36));
      const bx = Math.round((w - bw) / 2);
      const by = Math.max(2, Math.round(sky * 0.28));
      rect(bx, by, bw, 7, "#10141C");
      rect(bx + 1, by + 1, bw - 2, 5, "#0B0F16");
      const half = Math.floor((bw - 2) / 2);
      for (let x = bx + 2; x < bx + half; x += 2) rect(x, by + 2, 1, 3, o.accent);
      for (let x = bx + 2 + half; x < bx + bw - 2; x += 2) rect(x, by + 2, 1, 3, GOLD);
      rect(bx + Math.round(bw / 2) - 1, by + 7, 2, Math.max(0, sky - by - 7), GREY);
    }
  },
  // the made-up coach (owner: "make one up"): visor and headset, a play sheet, our colors, on the sideline
  coach(g, w, h, r, o) {
    const rect = rectOn(g);
    const us = o.us;
    const alt = o.accent;
    const ground = Math.round(h * 0.62);
    const top = Math.round(h * 0.18);
    rect(0, 0, w, h, SKY);
    rect(0, top, w, ground - top, "#3A3F4B");
    for (let y = top + 1; y < ground - 1; y += 2) for (let x = y % 4 ? 0 : 1; x < w; x += 2) rect(x, y, 1, 1, r() > 0.55 ? mix(us, "#3A3F4B", 0.35) : mix(alt, "#3A3F4B", 0.45));
    rect(0, ground, w, h - ground, FIELD);
    rect(0, ground, w, 1, CHALK);
    for (let y = ground + 3; y < h; y += 4) rect(0, y, w, 2, FIELD2);
    const fx = Math.round((w - 26) / 2);
    const fy = h - 34;
    const P = (x, y, pw, ph, c) => rect(fx + x, fy + y, pw, ph, c);
    const skin = "#C68E5A";
    const skinD = "#A8733F";
    const black = "#15171C";
    P(5, 17, 16, 17, us); P(3, 18, 2, 7, us); P(21, 18, 2, 7, us); // the team polo
    P(4, 18, 1, 1, mix(us, "#ffffff", 0.25)); P(5, 17, 16, 1, mix(us, "#ffffff", 0.2));
    P(3, 24, 2, 1, alt); P(21, 24, 2, 1, alt);
    P(10, 16, 6, 2, alt); P(11, 18, 4, 1, alt); P(12, 19, 2, 2, mix(us, "#000000", 0.25));
    P(6, 20, 2, 2, alt);
    P(3, 25, 2, 4, skin); P(21, 25, 2, 3, skin);
    P(8, 21, 13, 11, "#F3EBD3"); P(8, 21, 13, 1, alt); P(8, 31, 13, 1, mix("#F3EBD3", "#000000", 0.2)); P(8, 21, 1, 11, alt); P(20, 21, 1, 11, alt); // the play sheet
    for (const [x, y] of [[10, 23], [13, 23], [16, 23]]) { P(x, y, 1, 1, "#D32F2F"); P(x + 1, y + 1, 1, 1, "#D32F2F"); P(x + 1, y, 1, 1, "#D32F2F"); P(x, y + 1, 1, 1, "#D32F2F"); }
    for (const [x, y] of [[10, 28], [13, 28], [16, 28]]) { P(x, y, 2, 2, "#1E5AA8"); P(x, y, 1, 1, "#F3EBD3"); }
    P(12, 26, 4, 1, "#555555"); P(16, 25, 1, 2, "#555555");
    P(19, 27, 3, 3, skin); P(6, 28, 3, 3, skin); P(6, 28, 1, 1, skinD);
    P(11, 14, 4, 3, skin);
    P(9, 6, 8, 9, skin); P(8, 9, 1, 3, skin); P(17, 9, 1, 3, skinD);
    P(9, 9, 8, 2, black); P(10, 9, 2, 1, "#3A6EA5"); P(14, 9, 2, 1, "#3A6EA5"); // sunglasses with a glint
    P(11, 12, 4, 1, skinD); P(12, 13, 2, 1, "#7A3E2A");
    P(8, 5, 10, 2, us); P(8, 5, 10, 1, mix(us, "#ffffff", 0.25)); P(13, 6, 7, 2, mix(us, "#000000", 0.2)); P(18, 7, 2, 1, mix(us, "#000000", 0.35)); // the visor
    P(9, 3, 8, 2, "#4A3324");
    P(8, 2, 10, 1, black); P(7, 3, 1, 6, black); P(18, 3, 1, 5, black); // the headset
    P(6, 8, 3, 4, black); P(7, 9, 1, 2, "#555B66"); P(18, 8, 2, 4, black);
    P(8, 12, 2, 1, "#333333"); P(10, 13, 2, 1, "#333333"); P(12, 13, 1, 1, "#111111");
  },
  // a player with no headshot: head and shoulders, his number, our colors
  player(g, w, h, r, o) {
    const rect = rectOn(g);
    const us = o.us;
    const alt = o.accent;
    rect(0, 0, w, h, mix(us, "#0E1117", 0.55));
    for (let y = 0; y < h; y += 1) {
      for (let x = 0; x < w; x += 1) {
        const d = ((x - w / 2) / (w * 0.55)) ** 2 + ((y - h * 0.4) / (h * 0.55)) ** 2;
        if (d < 1) rect(x, y, 1, 1, d < 0.45 ? mix(us, "#0E1117", 0.3) : mix(us, "#0E1117", 0.42));
      }
    }
    const fx = Math.round((w - 24) / 2);
    const fy = h - 30;
    const P = (x, y, pw, ph, c) => rect(fx + x, fy + y, pw, ph, c);
    const skin = "#8D5B3A";
    const skinD = mix(skin, "#000000", 0.22);
    const hair = "#1C1410";
    P(1, 18, 22, 12, us); P(0, 20, 1, 10, us); P(23, 20, 1, 10, us);
    P(1, 18, 22, 1, mix(us, "#ffffff", 0.25)); P(2, 21, 3, 1, alt); P(19, 21, 3, 1, alt);
    P(8, 17, 8, 2, alt); P(9, 19, 6, 1, alt); P(10, 20, 4, 1, alt);
    P(10, 17, 4, 2, skin); P(11, 19, 2, 1, skin);
    const num = /^\d{1,2}$/.test(String(o.number ?? "")) ? String(o.number) : "";
    if (num) digits(g, num, fx + Math.round((24 - (num.length * 4 - 1)) / 2), fy + 22, CHALK);
    P(9, 14, 6, 4, skinD);
    P(7, 4, 10, 11, skin); P(6, 8, 1, 3, skinD); P(17, 8, 1, 3, skinD);
    P(7, 2, 10, 3, hair); P(6, 3, 1, 4, hair); P(17, 3, 1, 4, hair);
    P(9, 8, 2, 1, "#111111"); P(13, 8, 2, 1, "#111111");
    P(8, 10, 3, 1, "#111111"); P(13, 10, 3, 1, "#111111");
    P(11, 10, 2, 2, skinD); P(10, 13, 4, 1, "#5A2E22");
  },
};

// each picture's grid: at least this many rows and columns, the other side from the box's shape
const GRID = { helmet: [34, 37], stadium: [26, 16], coach: [38, 28], player: [32, 26] };

/** Size the canvas grid to the box's shape and paint it; nothing happens before the box has a size. */
function paintFill(canvas, kind, o) {
  const g = typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  const box = typeof canvas.getBoundingClientRect === "function" ? canvas.getBoundingClientRect() : null;
  if (!g || !box || !(box.width >= 4) || !(box.height >= 4)) return false;
  const [rows, cols] = GRID[kind];
  const h = Math.max(rows, Math.ceil((cols * box.height) / box.width));
  const w = Math.max(cols, Math.round((h * box.width) / box.height));
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  g.clearRect(0, 0, w, h);
  try {
    if (kind === "player" && o.face) {
      g.fillStyle = mix(o.us, "#0E1117", 0.35);
      g.fillRect(0, 0, w, h);
      const scale = h / o.face.naturalHeight;
      const width = o.face.naturalWidth * scale;
      g.imageSmoothingEnabled = true;
      g.drawImage(o.face, (w - width) / 2, 0, width, h); // the headshot crunched into the grid's pixels
    } else {
      FILL[kind](g, w, h, rng(o.seed || 7), o);
    }
  } catch (error) {
    console.warn(`A pixel ${kind} could not be drawn.`, error);
  }
  return true;
}

/**
 * A picture that fills its box (helmet, stadium, coach, player). The colors come from opts (a helmet's team) or the
 * page's own team tokens. It draws itself once its box has a size: refitPictures(root) after a layout or a resize.
 */
export function fillPicture(kind, opts = {}, label = "") {
  const k = Object.hasOwn(FILL, kind) ? kind : "stadium";
  const canvas = document.createElement("canvas");
  canvas.width = 40;
  canvas.height = 24;
  canvas.className = `px-pic px-fill px-fill--${k}`;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", typeof label === "string" && label ? label : `A pixel ${k}`);
  const theme = themeColors();
  const o = { ...(opts && typeof opts === "object" ? opts : {}) };
  o.us = hex6(o.us) || hex6(theme.us) || "#3D6BFF";
  o.accent = hex6(o.accent) || hex6(theme.accent) || "#FA4616";
  canvas.pxDraw = () => paintFill(canvas, k, o);
  const id = k === "player" && typeof o.playerId === "string" && /^\d{1,12}$/.test(o.playerId) ? o.playerId : null;
  if (id && typeof Image === "function") {
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        o.face = img;
        canvas.classList.add("px-pic--face");
        canvas.pxDraw();
      }
    };
    img.onerror = () => {}; // no headshot: the stand-in stays
    img.src = `/media/headshot/${id}`;
  }
  return canvas;
}

/** Redraw every fill picture under root at its box's size. */
export function refitPictures(root) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  for (const canvas of root.querySelectorAll("canvas.px-fill")) {
    if (typeof canvas.pxDraw === "function") canvas.pxDraw();
  }
}
