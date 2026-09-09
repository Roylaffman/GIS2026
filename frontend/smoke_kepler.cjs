// Headless smoke test: mount kepler.gl UMD page in jsdom to catch runtime
// errors in the redux wiring / component mount (WebGL won't render, but the
// React tree + store + addDataToMap dispatch will execute).
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "web");
const dom = new JSDOM("<!DOCTYPE html><html><body><div id='app'></div><div id='err'></div></body></html>", {
  url: "http://127.0.0.1:8090/kepler.html",
  pretendToBeVisual: true,
  runScripts: "outside-only",
});
const { window } = dom;

// Minimal globals the UMD bundles expect
window.fetch = (url) => {
  const p = path.join(WEB, String(url).split("/").pop());
  if (fs.existsSync(p)) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf-8"))),
    });
  }
  // real network (icons/basemap style) — resolve empty to keep test deterministic
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));
window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
window.cancelAnimationFrame = clearTimeout;
window.HTMLCanvasElement.prototype.getContext = () => ({});

// Web Fetch API globals that kepler.gl's bundled AI assistant expects at load time
for (const k of ["Request", "Response", "Headers", "FormData", "Blob", "File", "URL", "fetch", "AbortController"]) {
  if (typeof globalThis[k] !== "undefined" && window[k] === undefined) {
    window[k] = globalThis[k];
  }
}
window.Worker = window.Worker || class Worker { constructor() {} postMessage() {} terminate() {} };
window.URL.createObjectURL = window.URL.createObjectURL || (() => "");
window.URL.revokeObjectURL = window.URL.revokeObjectURL || (() => {});

// Capture console + errors
const errors = [];
window.addEventListener("error", (e) => errors.push(e.message));

function load(src) {
  const file = path.join(WEB, "lib", path.basename(src));
  const code = fs.readFileSync(file, "utf-8");
  const script = new window.Function(code);
  script.call(window);
}

// load in dependency order
const libs = ["react.production.min.js", "react-dom.production.min.js",
              "redux.min.js", "react-redux.min.js", "styled-components.min.js",
              "keplergl.min.js"];
for (const l of libs) {
  try { load(l); console.log("loaded", l); }
  catch (e) { console.log("FAILED loading", l, "->", e.message); process.exit(1); }
}

console.log("window.KeplerGl keys:", Object.keys(window.KeplerGl).slice(0, 12).join(", "));
console.log("default is component (fn):", typeof window.KeplerGl.default);

// run the page's inline script
const html = fs.readFileSync(path.join(WEB, "kepler.html"), "utf-8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
const inline = m[1];

// stub the config.js part
window.DSH_CONFIG = { mapboxToken: "" };

try {
  const script = new window.Function(inline);
  script.call(window);
  console.log("inline script ran without throwing");
} catch (e) {
  console.log("INLINE SCRIPT ERROR:", e.message);
  process.exit(1);
}

// let microtasks (fetch -> addDataToMap) run
setTimeout(() => {
  console.log("window errors:", errors.length ? errors : "none");
  console.log("document title:", window.document.title);
  const errEl = window.document.getElementById("err");
  console.log("err banner shown:", errEl.style.display === "block", "|", errEl.textContent);
  process.exit(0);
}, 1500);
