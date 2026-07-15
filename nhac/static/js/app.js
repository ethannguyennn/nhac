/* Nhạc — minimal vanilla JS. No external dependencies (works offline). */
window.Nhac = (function () {
  "use strict";

  /** Upload page: enable submit on file pick, show a processing state on submit. */
  function initUpload() {
    const input = document.getElementById("file-input");
    const label = document.getElementById("dz-label");
    const dz = document.querySelector(".dropzone");
    const btn = document.getElementById("submit-btn");
    const form = document.getElementById("upload-form");
    const progress = document.getElementById("progress");
    if (!input || !form) return;

    input.addEventListener("change", function () {
      const file = input.files && input.files[0];
      if (file) {
        label.textContent = file.name;
        dz.classList.add("has-file");
        btn.disabled = false;
      }
    });

    form.addEventListener("submit", function () {
      btn.disabled = true;
      btn.classList.add("hidden");
      progress.classList.remove("hidden");
    });
  }

  /** Player page: audio-reactive visualizer behind the video (warm bars). */
  function initVisualizer() {
    const video = document.getElementById("clip-video");
    const canvas = document.getElementById("viz");
    if (!video || !canvas) return;

    const ctx = canvas.getContext("2d");
    let audioCtx, analyser, data, raf, source;

    function resize() {
      canvas.width = canvas.clientWidth * devicePixelRatio;
      canvas.height = canvas.clientHeight * devicePixelRatio;
    }
    window.addEventListener("resize", resize);
    resize();

    function ensureAudio() {
      if (audioCtx) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      try {
        audioCtx = new AC();
        source = audioCtx.createMediaElementSource(video);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 128;
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
        data = new Uint8Array(analyser.frequencyBinCount);
      } catch (e) {
        /* CORS-tainted or unsupported: fall back to idle gradient */
        audioCtx = null;
      }
    }

    function draw() {
      raf = requestAnimationFrame(draw);
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      // Warm ambient wash.
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "rgba(224,164,88,0.10)");
      g.addColorStop(1, "rgba(201,111,111,0.06)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      if (!analyser) return;
      analyser.getByteFrequencyData(data);
      const bars = data.length;
      const bw = w / bars;
      for (let i = 0; i < bars; i++) {
        const v = data[i] / 255;
        const bh = v * h * 0.7;
        ctx.fillStyle = "rgba(224,164,88," + (0.15 + v * 0.5) + ")";
        ctx.fillRect(i * bw, h - bh, bw * 0.8, bh);
      }
    }

    video.addEventListener("play", function () {
      ensureAudio();
      if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
      if (!raf) draw();
    });
    draw(); // idle gradient before playback
  }

  return { initUpload: initUpload, initVisualizer: initVisualizer };
})();
