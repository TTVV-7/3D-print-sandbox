// Renders the shape tiles' icon frames for src/gen_tile_icons.py.
//
// Reads {jobs: [{name, glb}], w, h, frames, sway} on stdin, loads each GLB in
// headless Chromium with the same three.js, lighting and tone mapping as the
// pet tag's product shot, and writes {name: [png data URL per frame]} to
// stdout.  three.js is fetched from jsdelivr with curl and handed to the page,
// so a proxy that headless Chromium dislikes does not matter.
const fs = require("fs");
const { execFileSync, execSync } = require("child_process");
const { chromium } = require(execSync("npm root -g").toString().trim() + "/playwright");

const THREE = "https://cdn.jsdelivr.net/npm/three@0.170.0/";

const page_html = `<!doctype html><html><body style="margin:0;background:transparent">
<script type="importmap">{ "imports": { "three": "${THREE}build/three.module.js",
  "three/addons/": "${THREE}examples/jsm/" } }</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
window.render = async (b64, w, h, frames, sway) => {
  const r = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  r.setPixelRatio(1); r.setSize(w, h); r.setClearColor(0x000000, 0);
  r.toneMapping = THREE.ACESFilmicToneMapping;
  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture;
  const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(60, 90, 120); scene.add(key);
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
  const gltf = await new Promise((ok, bad) => new GLTFLoader().parse(bytes, "", ok, bad));
  const group = new THREE.Group(); group.add(gltf.scene); scene.add(group);
  const box = new THREE.Box3().setFromObject(group);
  const mid = box.getCenter(new THREE.Vector3());
  gltf.scene.position.sub(mid);                    // sway about its own middle
  // Framed on the object's own width and height rather than its diagonal,
  // so a flat tag fills a 60 px icon; the margin is what the sway and the
  // depth need.
  const size = box.getSize(new THREE.Vector3());
  const cam = new THREE.PerspectiveCamera(24, w / h, 0.1, 5000);
  const t = Math.tan(THREE.MathUtils.degToRad(12));
  const d = Math.max(size.y / 2 / t, size.x / 2 / (t * w / h)) * 1.14 + size.z / 2;
  cam.position.set(0, d * 0.2, d); cam.lookAt(0, 0, 0);
  const out = [];
  for (let k = 0; k < frames; k++) {
    group.rotation.y = sway * Math.sin(2 * Math.PI * k / frames);
    r.render(scene, cam);
    out.push(r.domElement.toDataURL("image/png"));
  }
  r.dispose();
  return out;
};
document.title = "ready";
</script></body></html>`;

(async () => {
  const spec = JSON.parse(fs.readFileSync(0, "utf8"));
  const browser = await chromium.launch({
    args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
           "--ignore-gpu-blocklist"] });
  const page = await browser.newPage();
  await page.route(THREE + "**", route => route.fulfill({
    status: 200, contentType: "application/javascript",
    body: execFileSync("curl", ["-sS", route.request().url()], { maxBuffer: 64 << 20 }) }));
  await page.route("http://icons.local/", route => route.fulfill({
    status: 200, contentType: "text/html", body: page_html }));
  await page.goto("http://icons.local/");
  await page.waitForFunction(() => document.title === "ready" && window.render);
  const result = {};
  for (const job of spec.jobs) {
    const b64 = fs.readFileSync(job.glb).toString("base64");
    result[job.name] = await page.evaluate(
      ([b, w, h, n, s]) => window.render(b, w, h, n, s), [b64, spec.w, spec.h, spec.frames, spec.sway]);
  }
  await browser.close();
  process.stdout.write(JSON.stringify(result));
})().catch(e => { console.error(e); process.exit(1); });
