const video = document.getElementById("cam");
const startBtn = document.getElementById("start");
const shotBtn = document.getElementById("shot");
const status = document.getElementById("status");
const early = document.getElementById("early");
const late = document.getElementById("late");
const controls = document.getElementById("controls");
const zoom = document.getElementById("zoom");
const zoomImg = document.getElementById("zoom-img");
const zoomCaption = document.getElementById("zoom-caption");

const EARLY = new Set([
  "raw",
  "fitted",
  "face",
  "prob",
  "mask_before",
  "mask_after",
  "cutout",
  "crop",
]);

const FIELDS = [
  "sigma",
  "phi",
  "contrast",
  "bilateral",
  "ink_high",
  "ink_span",
  "speck_area",
  "min_stroke_px",
  "simplify_px",
  "max_draw_seconds",
];

let captureId = null;
let timer = 0;
let inflight = false;
let pending = false;

function detailOf(data) {
  if (!data) return "falló";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg || String(item)).join(" ");
  return "falló";
}

function readTune() {
  const body = { id: captureId };
  for (const name of FIELDS) {
    const input = document.getElementById(name);
    body[name] = name === "speck_area" ? parseInt(input.value, 10) : Number(input.value);
  }
  return body;
}

function syncOutputs() {
  for (const name of FIELDS) {
    const input = document.getElementById(name);
    document.getElementById("val-" + name).textContent = input.value;
  }
}

function figureFor(layer) {
  const fig = document.createElement("figure");
  fig.dataset.id = layer.id;
  const img = document.createElement("img");
  img.src = layer.image;
  img.alt = layer.title;
  img.addEventListener("click", () => {
    zoomImg.src = layer.image;
    zoomImg.alt = layer.title;
    zoomCaption.textContent = layer.title + ". " + layer.note;
    zoom.showModal();
  });
  const caption = document.createElement("figcaption");
  const title = document.createElement("strong");
  title.textContent = layer.title;
  const note = document.createElement("span");
  note.textContent = layer.note + " " + layer.width + "×" + layer.height + ".";
  caption.append(title, note);
  fig.append(img, caption);
  return fig;
}

function place(layers) {
  for (const layer of layers) {
    const host = EARLY.has(layer.id) ? early : late;
    const next = figureFor(layer);
    const prev = host.querySelector(`[data-id="${layer.id}"]`);
    if (prev) prev.replaceWith(next);
    else host.append(next);
  }
}

async function sendTune() {
  if (!captureId) return;
  if (inflight) {
    pending = true;
    return;
  }
  inflight = true;
  pending = false;
  const body = readTune();
  try {
    const res = await fetch("/api/retune", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(detailOf(data));
    if (data.id === captureId) place(data.layers);
  } catch (err) {
    status.textContent = err.message;
  } finally {
    inflight = false;
    if (pending) sendTune();
  }
}

function scheduleTune() {
  syncOutputs();
  if (!captureId) return;
  clearTimeout(timer);
  timer = setTimeout(sendTune, 180);
}

startBtn.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: false,
    });
    video.srcObject = stream;
    startBtn.disabled = true;
    shotBtn.disabled = false;
    status.textContent = "Cuando estés, toma la foto.";
  } catch (err) {
    status.textContent = "No se pudo abrir la cámara. " + err.message;
  }
});

shotBtn.addEventListener("click", async () => {
  if (!video.videoWidth) return;
  const frame = document.createElement("canvas");
  frame.width = video.videoWidth;
  frame.height = video.videoHeight;
  frame.getContext("2d").drawImage(video, 0, 0);
  const image = frame.toDataURL("image/jpeg", 0.92);
  shotBtn.disabled = true;
  document.body.classList.add("busy");
  status.textContent = "Procesando la foto.";
  try {
    const res = await fetch("/api/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(detailOf(data));
    captureId = data.id;
    early.replaceChildren();
    late.replaceChildren();
    place(data.layers);
    controls.hidden = false;
    const face = data.face ? "con cara" : "sin cara";
    status.textContent = "Listo en " + (data.ms / 1000).toFixed(1) + " s, " + face + ".";
  } catch (err) {
    status.textContent = err.message;
  } finally {
    shotBtn.disabled = false;
    document.body.classList.remove("busy");
  }
});

controls.addEventListener("input", scheduleTune);

zoom.addEventListener("click", () => zoom.close());
