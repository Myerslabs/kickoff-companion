// Keep the screen on, with or without HTTPS (public release Phase 4b).
//
// Browsers give the Screen Wake Lock API only to secure pages (HTTPS or localhost). Since Phase 4b
// the app is served over plain HTTP on the home network, so a phone or tablet usually has no
// navigator.wakeLock. screenLock() hands back the real API when there is one, and otherwise an
// object with the same shape (request("screen") resolving to a sentinel with released, release()
// and a "release" event) that keeps the screen awake the long-standing way: a tiny muted video
// (static/media/awake.mp4, one black second) playing on a loop in a hidden corner. A playing video
// keeps the display on in every mobile browser.
//
// Browsers only start playback after a tap, so the fallback waits for the first touch or click on
// the page when the request comes before one; the sentinel is handed out at once and the video
// starts on that first tap. The video is muted, inline, 1 by 1 pixel and transparent, and never
// takes focus or audio.

const VIDEO_SOURCES = [
  ["/static/media/awake.mp4", "video/mp4"],
  ["/static/media/awake.webm", "video/webm"],
];

let video = null;
let holders = 0;
let waitingForTap = false;

function makeVideo() {
  const node = document.createElement("video");
  node.setAttribute("muted", "");
  node.setAttribute("playsinline", "");
  node.setAttribute("loop", "");
  node.setAttribute("aria-hidden", "true");
  node.setAttribute("tabindex", "-1");
  node.muted = true;
  node.playsInline = true;
  node.loop = true;
  node.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;opacity:0;pointer-events:none;";
  for (const [src, type] of VIDEO_SOURCES) {
    const source = document.createElement("source");
    source.setAttribute("src", src);
    source.setAttribute("type", type);
    node.append(source);
  }
  return node;
}

function play() {
  if (!video || holders <= 0 || video.paused === false) return; // already playing
  let started;
  try {
    started = video.play();
  } catch (error) {
    started = Promise.reject(error);
  }
  if (started && typeof started.catch === "function") {
    started.catch(() => waitForTap()); // not allowed before a tap: try again on the first one
  }
}

function waitForTap() {
  if (waitingForTap) return;
  waitingForTap = true;
  const onTap = () => {
    waitingForTap = false;
    document.removeEventListener("pointerdown", onTap, true);
    document.removeEventListener("touchend", onTap, true);
    document.removeEventListener("click", onTap, true);
    play();
  };
  document.addEventListener("pointerdown", onTap, true);
  document.addEventListener("touchend", onTap, true);
  document.addEventListener("click", onTap, true);
}

function hold() {
  holders += 1;
  if (!video) {
    video = makeVideo();
    document.body.append(video);
  }
  play();
}

function letGo() {
  holders = Math.max(0, holders - 1);
  if (holders === 0 && video) {
    try {
      video.pause();
    } catch {
      // a video that never started has nothing to pause
    }
  }
}

class VideoSentinel {
  constructor() {
    this.type = "screen";
    this.released = false;
    this.listeners = new Set();
    hold();
  }

  addEventListener(name, listener) {
    if (name === "release" && typeof listener === "function") this.listeners.add(listener);
  }

  removeEventListener(name, listener) {
    if (name === "release") this.listeners.delete(listener);
  }

  async release() {
    if (this.released) return;
    this.released = true;
    letGo();
    for (const listener of [...this.listeners]) {
      try {
        listener(new Event("release"));
      } catch (error) {
        console.warn(`Keep screen on: a release listener failed: ${error?.message || error}`);
      }
    }
  }
}

const videoLock = {
  fallback: true,
  async request(type = "screen") {
    if (type !== "screen") throw new TypeError(`Unsupported wake lock type ${type}`);
    return new VideoSentinel();
  },
};

/** The screen wake lock: the browser's own when it has one, else the video fallback; null when neither can work. */
export function screenLock() {
  if (typeof navigator !== "undefined" && navigator.wakeLock && typeof navigator.wakeLock.request === "function") return navigator.wakeLock;
  if (typeof document === "undefined" || typeof document.createElement !== "function") return null;
  return videoLock;
}

/** For the tests: how many holders the fallback has and whether its video exists. */
export function fallbackState() {
  return { holders, hasVideo: Boolean(video), waitingForTap };
}
