// The newspaper's type fitted to its boxes (queue items 10 to 12, mock approved 2026-10-13: "The text and picture should
// fill the screen like a newspaper"). Every box in a row is one height, and each box's headline takes the largest size
// that keeps the box inside that height; a team's name under its helmet stays on one line by shrinking (then by its
// abbreviation). The browser lays the page out a few dozen times in all: every box is measured in the same pass, never
// one at a time (the mock's one-box search laid the page out about a thousand times, seconds on an iPad).
//
//   fitNames(root)                      every [data-oneline] element on one line: shrink to fit (never under data-min),
//                                       then its data-short text; returns the texts that still do not fit
//   loosenNames(root)                   a name kept whole (.paper-nw) wider than its own column may break between its
//                                       words after all (a headline is prose; only scores and records never break)
//   fitRows(rows)                       rows: [{ row, boxes, primary, target, minHeight }]; each box's [data-fit] element
//                                       carries data-cap and data-min (px). Returns each row's height.
//
// Nothing happens in a box with no size (a page not on screen, the test browser): the CSS sizes stand.

const ITERATIONS = 12; // halvings of the size range: within a quarter pixel of the best size

const num = (value, fallback) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

const height = (el) => (el && typeof el.getBoundingClientRect === "function" ? el.getBoundingClientRect().height || 0 : 0);

/** True when anything inside the fitted element sticks out sideways (a word or a name kept whole wider than its column). */
function sticksOut(fit) {
  if (!fit) return false;
  if (fit.scrollWidth > fit.clientWidth + 1) return true;
  for (const node of fit.querySelectorAll("*")) {
    if (node.scrollWidth > node.clientWidth + 1 && getComputedStyle(node).display !== "inline") return true;
  }
  return false;
}

export function fitNames(root) {
  const items = [...(root?.querySelectorAll?.("[data-oneline]") || [])];
  const problems = [];
  if (!items.length) return problems;
  for (const el of items) {
    el.style.fontSize = "";
    el.style.whiteSpace = "nowrap";
    if (el.dataset.full && !el.children.length) el.textContent = el.dataset.full;
  }
  const over = (el) => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 0.5;
  // text width grows with its size: one measured pass picks each size, a second confirms it
  for (let pass = 0; pass < 3; pass += 1) {
    const todo = items.filter(over);
    if (!todo.length) break;
    const sizes = todo.map((el) => {
      const now = parseFloat(getComputedStyle(el).fontSize) || 16;
      const min = num(el.dataset.min, 14);
      return Math.max(min, Math.floor(((now * el.clientWidth) / el.scrollWidth) * 2) / 2 - (pass ? 0.5 : 0));
    });
    todo.forEach((el, i) => {
      el.style.fontSize = `${sizes[i]}px`;
    });
  }
  for (const el of items.filter(over)) {
    if (el.dataset.short && !el.children.length) {
      el.dataset.full = el.dataset.full || el.textContent;
      el.textContent = el.dataset.short;
    }
  }
  for (const el of items.filter(over)) problems.push((el.textContent || "").slice(0, 40));
  return problems;
}

export function loosenNames(root) {
  for (const span of root?.querySelectorAll?.(".paper-nw") || []) {
    const col = span.closest("h3, p, div");
    if (col && col.clientWidth > 0 && span.getBoundingClientRect().width > col.clientWidth - 1 && /\s/.test(span.textContent || "")) span.classList.remove("paper-nw");
  }
}

/**
 * Fit rows of boxes to one height each. A row's height is its primary box's at the target size (the lead story), else
 * its shortest box's at its top size, raised to what every box needs at its smallest. Then every box at once takes the
 * largest size that keeps it within its row's height and sticks out nowhere.
 */
export function fitRows(rows) {
  const specs = (Array.isArray(rows) ? rows : []).filter((r) => r && r.row && Array.isArray(r.boxes) && r.boxes.length);
  const boxes = [];
  for (const spec of specs) {
    spec.items = spec.boxes.map((box, i) => {
      box.style.height = "auto";
      const fit = box.querySelector("[data-fit]");
      const cap = num(fit?.dataset.cap, 30);
      const min = num(fit?.dataset.min, 16);
      const top = Math.max(min, i === spec.primary && num(spec.target, 0) ? Math.min(cap, spec.target) : cap);
      const item = { box, fit, min, cap: Math.max(cap, min), top }; // a cap under its floor is the floor (never under 13 px text)
      boxes.push(item);
      return item;
    });
  }
  if (!boxes.length || !(specs[0].row.clientWidth > 0)) return specs.map(() => 0);
  const setAll = (pick) => {
    for (const b of boxes) if (b.fit) b.fit.style.fontSize = `${pick(b)}px`;
  };
  // the largest size at which nothing sticks out sideways: a size that is too wide is too big, whatever the height
  setAll((b) => b.top);
  loosenNames(specs[0].row.parentNode || specs[0].row);
  for (const b of boxes) {
    b.lo = b.min;
    b.hi = b.top;
    b.wideOk = !sticksOut(b.fit);
  }
  for (let i = 0; i < ITERATIONS && boxes.some((b) => !b.wideOk); i += 1) {
    setAll((b) => (b.wideOk ? b.hi : (b.lo + b.hi) / 2));
    for (const b of boxes) {
      if (b.wideOk) continue;
      const mid = (b.lo + b.hi) / 2;
      if (sticksOut(b.fit)) b.hi = mid;
      else b.lo = mid;
    }
  }
  for (const b of boxes) {
    if (!b.wideOk) b.top = b.lo;
  }
  // each row's height
  setAll((b) => b.top);
  for (const b of boxes) b.atTop = height(b.box);
  setAll((b) => b.min);
  for (const b of boxes) b.atMin = height(b.box);
  for (const spec of specs) {
    const primary = spec.items[spec.primary];
    let h = primary ? primary.atTop : Math.min(...spec.items.map((b) => b.atTop));
    h = Math.max(h, num(spec.minHeight, 0), ...spec.items.map((b) => b.atMin));
    spec.height = h;
    for (const b of spec.items) {
      b.limit = h;
      b.lo = b.min;
      b.hi = b.top;
      b.done = !b.fit || b.atTop <= h + 0.5;
      if (b.done) b.lo = b.top;
    }
    // a row the minimum height made taller than its lead: the lead grows into it, up to its top size
    if (primary && primary.fit && h > primary.atTop + 0.5 && primary.cap > primary.top) {
      primary.lo = primary.top;
      primary.hi = primary.cap;
      primary.done = false;
    }
  }
  // every box at once: the largest size within its row's height
  for (let i = 0; i < ITERATIONS && boxes.some((b) => !b.done); i += 1) {
    setAll((b) => (b.done ? b.lo : (b.lo + b.hi) / 2));
    for (const b of boxes) {
      if (b.done) continue;
      const mid = (b.lo + b.hi) / 2;
      if (height(b.box) <= b.limit + 0.5 && !sticksOut(b.fit)) b.lo = mid;
      else b.hi = mid;
    }
  }
  setAll((b) => Math.floor(b.lo * 4) / 4);
  for (const spec of specs) for (const b of spec.items) b.box.style.height = `${Math.ceil(spec.height)}px`;
  return specs.map((s) => s.height);
}
