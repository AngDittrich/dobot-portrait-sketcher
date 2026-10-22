const video = document.getElementById("cam");
const out = document.getElementById("out");
const meta = document.getElementById("meta");
const startBtn = document.getElementById("start");
const shotBtn = document.getElementById("shot");
const retryBtn = document.getElementById("retry");
let stream = null;

startBtn.onclick = async () => {
  stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
  video.srcObject = stream;
  shotBtn.disabled = false;
  startBtn.disabled = true;
};

shotBtn.onclick = async () => {
  const cap = document.createElement("canvas");
  cap.width = video.videoWidth;
  cap.height = video.videoHeight;
  cap.getContext("2d").drawImage(video, 0, 0);
  const image = cap.toDataURL("image/jpeg", 0.92);
  document.body.classList.add("busy");
  meta.textContent = "Quitando fondo…";
  shotBtn.disabled = true;
  try {
    const res = await fetch("/api/remove-bg", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "falló");
    const img = new Image();
    img.onload = () => {
      out.width = img.width;
      out.height = img.height;
      out.getContext("2d").drawImage(img, 0, 0);
      const t = data.timings_ms || {};
      meta.textContent = `cara: ${data.face_found ? "sí" : "no"} · ${t.total ?? "?"} ms (grabcut ${t.grabcut ?? "?"} ms) · bbox ${data.bbox.join("×")}`;
      retryBtn.disabled = false;
    };
    img.src = data.cutout_png;
    meta2.textContent = "Dibujando boceto…";
    const res2 = await fetch("/api/sketch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data2 = await res2.json();
    if (!res2.ok) throw new Error(data2.detail || "falló boceto");
    const sk = new Image();
    sk.onload = () => {
      const c = document.getElementById("sk");
      c.width = sk.width;
      c.height = sk.height;
      c.getContext("2d").drawImage(sk, 0, 0);
      const t2 = data2.timings_ms || {};
      document.getElementById("meta2").textContent =
        `boceto ${t2.total ?? "?"} ms · total ${t2.request ?? "?"} ms`;
    };
    sk.src = data2.sketch_png;
  } catch (err) {
    meta.textContent = "Error: " + err.message;
    shotBtn.disabled = false;
  } finally {
    document.body.classList.remove("busy");
  }
};

retryBtn.onclick = () => {
  out.getContext("2d").clearRect(0, 0, out.width, out.height);
  meta.textContent = "Sin captura todavía.";
  shotBtn.disabled = false;
  retryBtn.disabled = true;
};
