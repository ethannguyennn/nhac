/* Nhạc theater player.
 *
 * Reads the queue embedded in the page, shuffles by default, autoplays,
 * and keeps the screen video-only until the user moves the mouse / taps.
 * No dependencies.
 */
window.NhacPlayer = (function () {
  "use strict";

  var LS = { shuffle: "nhac.shuffle", hype: "nhac.hype", muted: "nhac.muted" };
  var IDLE_MS = 2800; // controls fade out after this much stillness
  var queue = [];
  var order = [];
  var pos = 0;
  var shuffle = true;
  var hype = false;
  var els = {};
  var idleTimer = null;
  var raf = null;
  var dragging = false;
  var errStreak = 0;
  var building = {}; // clip_id -> true while its hype cut is rendering server-side
  var backOnA = false; // which backdrop layer is showing

  /* ---------- tiny utils ---------- */

  function $(id) { return document.getElementById(id); }

  function lsGetBool(key, dflt) {
    var v = null;
    try { v = localStorage.getItem(key); } catch (e) { /* private mode */ }
    return v === null ? dflt : v === "1";
  }
  function lsSetBool(key, val) {
    try { localStorage.setItem(key, val ? "1" : "0"); } catch (e) { /* ignore */ }
  }

  function fmt(t) {
    if (!isFinite(t) || t < 0) t = 0;
    var m = Math.floor(t / 60);
    var s = Math.floor(t % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function shuffleArray(a) {
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
    }
  }

  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.add("show");
    clearTimeout(els.toast._t);
    els.toast._t = setTimeout(function () { els.toast.classList.remove("show"); }, 2400);
  }

  /* ---------- queue & order ---------- */

  function buildOrder(firstClipId) {
    order = queue.map(function (_, i) { return i; });
    if (shuffle) shuffleArray(order);
    if (firstClipId) {
      var qi = -1;
      for (var i = 0; i < queue.length; i++) {
        if (queue[i].clip_id === firstClipId) { qi = i; break; }
      }
      if (qi >= 0) {
        order.splice(order.indexOf(qi), 1);
        order.unshift(qi);
      }
    }
    pos = 0;
  }

  function current() { return queue[order[pos]]; }

  function srcFor(item) {
    return hype && item.montage_url ? item.montage_url : item.media_url;
  }

  /* ---------- loading & transport ---------- */

  function load(opts) {
    opts = opts || {};
    var item = current();
    if (!item) return;

    document.body.classList.remove("buffering"); // don't carry over a stale spinner
    els.video.src = srcFor(item);
    els.video.load();
    setBackdrop(item.thumbnail_url);

    els.nowTitle.textContent = item.title;
    els.nowArtist.textContent = item.artist || "";
    document.title = item.title + " · Nhạc";
    updateMediaSession(item);
    updateHypeButton();
    renderHighlightMarks(item);

    if (opts.intro !== false) playIntro(item);
    if (opts.autoplay !== false) attemptPlay();

    // Hype mode on but this track's montage isn't rendered yet: cook it in
    // the background so FUTURE plays of the track get the montage. (The
    // swap-in decision is made dynamically when the build finishes — see
    // requestMontage — so this never interrupts what's currently playing.)
    if (hype && !item.montage_url && !building[item.clip_id]) {
      requestMontage(item, { silent: true });
    }
  }

  /** Tick marks on the progress bar for this track's exciting moments. */
  function renderHighlightMarks(item) {
    var container = els.progressHighlights;
    if (!container) return;
    container.innerHTML = "";
    var duration = item.duration_seconds || els.video.duration;
    if (!duration || !isFinite(duration) || !item.highlights) return;
    item.highlights.forEach(function (h) {
      var left = (h.start_seconds / duration) * 100;
      var width = ((h.end_seconds - h.start_seconds) / duration) * 100;
      if (!isFinite(left) || !isFinite(width)) return;
      var mark = document.createElement("span");
      mark.className = "mark";
      mark.style.left = Math.max(0, Math.min(100, left)) + "%";
      mark.style.width = Math.max(0.4, Math.min(100, width)) + "%";
      container.appendChild(mark);
    });
  }

  function attemptPlay() {
    var p = els.video.play();
    if (p && p.then) {
      p.then(function () {
        els.startOverlay.hidden = true;
      }).catch(function () {
        els.startOverlay.hidden = false; // autoplay blocked → tap to start
      });
    }
  }

  function next(reshuffleOnWrap) {
    if (!queue.length) return;
    pos += 1;
    if (pos >= order.length) {
      var lastIdx = order[order.length - 1];
      buildOrder(null);
      // Avoid replaying the same track back-to-back after a reshuffle.
      if (reshuffleOnWrap !== false && shuffle && queue.length > 1 && order[0] === lastIdx) {
        order.push(order.shift());
      }
      pos = 0;
    }
    load({});
  }

  function prev() {
    if (els.video.currentTime > 3) {
      els.video.currentTime = 0;
      return;
    }
    pos = (pos - 1 + order.length) % order.length;
    load({});
  }

  function togglePlay() {
    if (els.video.paused) attemptPlay();
    else els.video.pause();
  }

  function toggleShuffle() {
    shuffle = !shuffle;
    lsSetBool(LS.shuffle, shuffle);
    var keep = current() ? current().clip_id : null;
    buildOrder(keep);
    els.btnShuffle.classList.toggle("on", shuffle);
    toast(shuffle ? "Shuffle on" : "Shuffle off");
  }

  /* ---------- hype cut ---------- */

  function updateHypeButton() {
    var item = current();
    els.btnHype.classList.toggle("on", hype);
    els.btnHype.classList.toggle("building", !!item && !!building[item.clip_id]);
  }

  // Kick off (or join) a montage build for `item`. Whether it swaps the
  // playing video when it lands is decided at COMPLETION time from live
  // state (hype on + still sitting on this track) — not frozen at request
  // start — so a background build that was silently started while browsing
  // still swaps in correctly if the user turns hype on before it finishes.
  function requestMontage(item, opts) {
    opts = opts || {};
    if (building[item.clip_id]) return building[item.clip_id]; // join in-flight build

    var promise = fetch("/api/clips/" + item.clip_id + "/montage", { method: "POST" })
      .then(function (res) {
        if (!res.ok) throw new Error("montage build failed (" + res.status + ")");
        return res.json();
      })
      .then(function (data) {
        item.montage_url = data.montage_url;
        delete building[item.clip_id];
        updateHypeButton();
        if (hype && current() === item) {
          load({ intro: false }); // swap to the now-ready hype cut
        } else if (!opts.silent) {
          toast("Hype cut ready ⚡");
        }
        return data;
      })
      .catch(function (err) {
        delete building[item.clip_id];
        updateHypeButton();
        if (!opts.silent) toast("Couldn't build the hype cut");
        throw err;
      });

    building[item.clip_id] = promise;
    updateHypeButton();
    return promise;
  }

  function toggleHype() {
    var item = current();
    if (!item) return;
    if (hype) {
      hype = false;
      lsSetBool(LS.hype, false);
      load({ intro: false });
      toast("Full takes");
      return;
    }
    hype = true;
    lsSetBool(LS.hype, true);
    if (item.montage_url) {
      load({ intro: false });
      toast("Hype cut ⚡");
    } else {
      toast("Cutting the hype reel…");
      requestMontage(item, { silent: false }).catch(function () {});
    }
    updateHypeButton();
  }

  /* ---------- visuals: backdrop, intro, eq ---------- */

  function setBackdrop(url) {
    var showEl = backOnA ? els.backdropB : els.backdropA;
    var hideEl = backOnA ? els.backdropA : els.backdropB;
    backOnA = !backOnA;
    showEl.style.backgroundImage = url ? "url('" + url + "')" : "none";
    showEl.classList.add("active");
    hideEl.classList.remove("active");
  }

  function playIntro(item) {
    els.tiTitle.textContent = item.title;
    els.tiArtist.textContent = item.artist || "";
    els.trackIntro.classList.remove("show");
    void els.trackIntro.offsetWidth; // restart the CSS animation
    els.trackIntro.classList.add("show");
  }

  /* ---------- idle chrome ---------- */

  function wakeUI() {
    document.body.classList.remove("idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      if (!els.video.paused && !dragging) document.body.classList.add("idle");
    }, IDLE_MS);
  }

  /* ---------- progress ---------- */

  function ratioFromEvent(ev) {
    var rect = els.progress.getBoundingClientRect();
    var x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
    return Math.min(1, Math.max(0, x / rect.width));
  }

  function renderProgress() {
    var v = els.video;
    if (v.duration) {
      els.progressFill.style.width = (v.currentTime / v.duration) * 100 + "%";
      els.timeNow.textContent = fmt(v.currentTime);
      els.timeTotal.textContent = fmt(v.duration);
      try {
        if (v.buffered.length) {
          els.progressBuffered.style.width =
            (v.buffered.end(v.buffered.length - 1) / v.duration) * 100 + "%";
        }
      } catch (e) { /* transient ranges */ }
    }
    raf = requestAnimationFrame(renderProgress);
  }

  /* ---------- media session (lock screen / OS controls) ---------- */

  function updateMediaSession(item) {
    if (!("mediaSession" in navigator)) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: item.title,
        artist: item.artist || "",
        album: "Nhạc",
        artwork: item.thumbnail_url
          ? [{ src: item.thumbnail_url, sizes: "512x512", type: "image/jpeg" }]
          : [],
      });
    } catch (e) { /* older browsers */ }
  }

  /* ---------- wiring ---------- */

  function bindEvents() {
    var v = els.video;

    v.addEventListener("play", function () {
      document.body.classList.add("playing");
      els.eq.classList.remove("paused");
      wakeUI();
    });
    v.addEventListener("pause", function () {
      document.body.classList.remove("playing");
      document.body.classList.remove("buffering"); // don't get stuck if paused mid-stall
      els.eq.classList.add("paused");
      wakeUI(); // keep controls visible while paused
      clearTimeout(idleTimer);
    });
    v.addEventListener("playing", function () {
      errStreak = 0;
      document.body.classList.remove("buffering");
    });
    v.addEventListener("ended", function () { next(); });
    // No native `controls`, so a stalled network/disk read is otherwise
    // silent — a frozen frame with zero feedback. Surface a spinner instead.
    v.addEventListener("waiting", function () { document.body.classList.add("buffering"); });
    v.addEventListener("canplay", function () { document.body.classList.remove("buffering"); });
    v.addEventListener("seeking", function () { document.body.classList.add("buffering"); });
    v.addEventListener("seeked", function () { document.body.classList.remove("buffering"); });
    // Re-render highlight marks once real duration is known — covers clips
    // whose duration_seconds wasn't probed (falls back to el.duration).
    v.addEventListener("loadedmetadata", function () {
      var item = current();
      if (item && !item.duration_seconds) renderHighlightMarks(item);
    });
    v.addEventListener("error", function () {
      if (!v.currentSrc) return;
      errStreak += 1;
      if (errStreak >= queue.length) {
        toast("Playback failed — check your media files");
        return;
      }
      toast("Couldn't play that one — skipping");
      setTimeout(function () { next(); }, 900);
    });

    // Click the stage: toggle on pointer devices, reveal chrome on touch.
    v.addEventListener("click", function () {
      if (window.matchMedia("(hover: hover)").matches) togglePlay();
      else wakeUI();
    });

    els.btnPlay.addEventListener("click", togglePlay);
    els.btnNext.addEventListener("click", function () { next(); });
    els.btnPrev.addEventListener("click", prev);
    els.btnShuffle.addEventListener("click", toggleShuffle);
    els.btnHype.addEventListener("click", toggleHype);
    els.btnMute.addEventListener("click", function () {
      v.muted = !v.muted;
      lsSetBool(LS.muted, v.muted);
      document.body.classList.toggle("muted", v.muted);
    });
    els.btnFs.addEventListener("click", function () {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen().catch(function () {});
    });

    els.startBtn.addEventListener("click", function () {
      els.startOverlay.hidden = true;
      attemptPlay();
    });

    // Seek: click + drag anywhere on the bar.
    els.progress.addEventListener("pointerdown", function (ev) {
      dragging = true;
      els.progress.classList.add("dragging");
      els.progress.setPointerCapture(ev.pointerId);
      if (v.duration) v.currentTime = ratioFromEvent(ev) * v.duration;
    });
    els.progress.addEventListener("pointermove", function (ev) {
      if (dragging && v.duration) v.currentTime = ratioFromEvent(ev) * v.duration;
    });
    function endDrag() {
      dragging = false;
      els.progress.classList.remove("dragging");
    }
    els.progress.addEventListener("pointerup", endDrag);
    els.progress.addEventListener("pointercancel", endDrag);

    // Idle detection.
    ["mousemove", "pointerdown", "touchstart"].forEach(function (evt) {
      window.addEventListener(evt, wakeUI, { passive: true });
    });

    // Keyboard.
    window.addEventListener("keydown", function (ev) {
      if (ev.target && /input|textarea|select/i.test(ev.target.tagName)) return;
      var k = ev.key.toLowerCase();
      if (k === " " || k === "k") { ev.preventDefault(); togglePlay(); }
      else if (k === "arrowright") { v.currentTime = Math.min((v.duration || 0), v.currentTime + 5); }
      else if (k === "arrowleft") { v.currentTime = Math.max(0, v.currentTime - 5); }
      else if (k === "n") { next(); }
      else if (k === "p") { prev(); }
      else if (k === "s") { toggleShuffle(); }
      else if (k === "h") { toggleHype(); }
      else if (k === "m") { els.btnMute.click(); }
      else if (k === "f") { els.btnFs.click(); }
      wakeUI();
    });

    if ("mediaSession" in navigator) {
      try {
        navigator.mediaSession.setActionHandler("play", togglePlay);
        navigator.mediaSession.setActionHandler("pause", togglePlay);
        navigator.mediaSession.setActionHandler("previoustrack", prev);
        navigator.mediaSession.setActionHandler("nexttrack", function () { next(); });
      } catch (e) { /* not all actions supported everywhere */ }
    }
  }

  /* ---------- init ---------- */

  function init(opts) {
    opts = opts || {};
    var data = JSON.parse($("queue-data").textContent);
    queue = data.items || [];

    els = {
      video: $("pv"),
      ui: $("ui"),
      backdropA: $("backdrop-a"),
      backdropB: $("backdrop-b"),
      nowTitle: $("now-title"),
      nowArtist: $("now-artist"),
      trackIntro: $("track-intro"),
      tiTitle: $("ti-title"),
      tiArtist: $("ti-artist"),
      progress: $("progress"),
      progressFill: $("progress-fill"),
      progressBuffered: $("progress-buffered"),
      progressHighlights: $("progress-highlights"),
      timeNow: $("time-now"),
      timeTotal: $("time-total"),
      btnPlay: $("btn-play"),
      btnPrev: $("btn-prev"),
      btnNext: $("btn-next"),
      btnShuffle: $("btn-shuffle"),
      btnHype: $("btn-hype"),
      btnMute: $("btn-mute"),
      btnFs: $("btn-fs"),
      startOverlay: $("start-overlay"),
      startBtn: $("start-btn"),
      eq: $("eq"),
      toast: $("toast"),
    };

    if (!queue.length) return;

    shuffle = lsGetBool(LS.shuffle, true); // shuffle is the default experience
    hype = lsGetBool(LS.hype, false);
    els.video.muted = lsGetBool(LS.muted, false);
    document.body.classList.toggle("muted", els.video.muted);
    els.btnShuffle.classList.toggle("on", shuffle);

    bindEvents();
    buildOrder(opts.startTrack || null);
    load({});
    renderProgress();
    wakeUI();
  }

  return { init: init };
})();
