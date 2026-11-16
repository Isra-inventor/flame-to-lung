import * as THREE from "/static/vendor/three.module.min.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
// ==================== ERRORS SHOWN ON THE PAGE ====================
function report(where, error) {
  console.error(where, error);
  let box = $("#errors");
  if (!box) { box = document.createElement("pre"); box.id = "errors"; document.body.append(box); }
  box.textContent += `${where}: ${error?.message || error}\n`;
}
addEventListener("error", e => report("script", e.error || e.message));
addEventListener("unhandledrejection", e => report("request", e.reason));
async function getJson(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) throw new Error(`${url} answered ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.json();
}
const post = (url, body) => getJson(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const REGION = { HA: ["Head airways", "#3987e5"], TB: ["Bronchi", "#d95926"], AL: ["Alveoli", "#199e70"] };
const INK = "#eef0f2", INK2 = "#a9b0ba", GRID = "rgba(238,240,242,.07)";
const pct = x => (100 * x).toFixed(1) + "%";
const big = x => x >= 1e9 ? (x / 1e9).toFixed(1) + " billion" : x >= 1e6 ? (x / 1e6).toFixed(1) + " million" : Math.round(x).toLocaleString();
const sig = (x, n = 3) => Number(x.toPrecision(n)).toString();

// ==================== 3D SCENE: FLAME, SMOKE, LUNG ====================
function buildScene() {
  const canvas = $("#space");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0x06080c);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.z = 9;

  const vertex = `
    attribute vec3 color; attribute float size; attribute float seed; attribute float region;
    uniform float uTime, uOpacity, uPx, uWobble, uDrift, uGrow; uniform vec3 uLevels;
    varying vec3 vColor; varying float vAlpha;
    void main() {
      float level = region < 0.5 ? uLevels.x : region < 1.5 ? uLevels.y : region < 2.5 ? uLevels.z : 1.0;
      vec3 p = position * (1.0 + uWobble * sin(uTime * 1.7 + seed * 40.0));
      p.x = mix(p.x, mod(p.x + uTime * uDrift * (0.4 + seed) + 12.0, 24.0) - 12.0, step(0.0001, uDrift));
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      gl_Position = projectionMatrix * mv;
      gl_PointSize = size * uGrow * uPx * 3.4 * (0.6 + 0.8 * level) / -mv.z;
      vAlpha = uOpacity * (0.16 + 0.84 * level) * (0.72 + 0.28 * sin(uTime * 1.3 + seed * 60.0));
      vColor = color;
    }`;
  const fragment = `
    varying vec3 vColor; varying float vAlpha;
    void main() {
      float glow = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5));
      gl_FragColor = vec4(vColor, glow * glow * vAlpha);
    }`;

  function cloud(points, extra = {}) {
    const geo = new THREE.BufferGeometry();
    const attr = (name, n, pick) => geo.setAttribute(name, new THREE.Float32BufferAttribute(points.flatMap(pick), n));
    attr("position", 3, p => p.pos); attr("color", 3, p => p.color);
    attr("size", 1, p => [p.size]); attr("seed", 1, () => [Math.random()]); attr("region", 1, p => [p.region ?? 3]);
    const uniforms = { uTime: { value: 0 }, uOpacity: { value: 1 }, uPx: { value: 1 }, uWobble: { value: 0 },
      uDrift: { value: 0 }, uGrow: { value: 1 }, uLevels: { value: new THREE.Vector3(.3, .3, .3) } };
    Object.entries(extra).forEach(([k, v]) => uniforms[k].value = v);
    const mesh = new THREE.Points(geo, new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: fragment, uniforms,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    mesh.frustumCulled = false;
    scene.add(mesh);
    return mesh;
  }

  const rgb = hex => new THREE.Color(hex).toArray();
  const rand = (a = 1) => (Math.random() - 0.5) * 2 * a;
  const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

  // ---------- flame: a blue sphere, the shape fire takes without gravity ----------
  const flamePoints = [];
  for (let i = 0; i < 5200; i++) {
    const r = Math.random() < 0.55 ? 0.95 + gauss() * 0.12 : Math.pow(Math.random(), 0.5) * 1.3;
    const u = rand(), t = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const color = r < 0.35 ? rgb("#f2f7ff") : r < 0.85 ? rgb("#3f8cff") : r < 1.12 ? rgb("#2748e8") : rgb("#b0621c");
    flamePoints.push({ pos: [r * s * Math.cos(t), r * u, r * s * Math.sin(t)], color, size: r < 0.35 ? 26 : r < 1.12 ? 15 : 6 });
  }
  const flame = cloud(flamePoints, { uWobble: 0.035 });

  // ---------- smoke: drifting soot particles ----------
  const smokePoints = Array.from({ length: 1500 }, () => ({ pos: [rand(12), rand(5), rand(4) - 1], color: rgb("#8d8478"), size: 5 + Math.random() * 9 }));
  const smoke = cloud(smokePoints, { uDrift: 0.12, uOpacity: 0.55 });

  // ---------- lung: a branching airway tree with alveoli at the tips ----------
  const lungPoints = [];
  const along = (a, b, n, spread, color, size, region) => {
    for (let i = 0; i < n; i++) {
      const k = Math.random();
      lungPoints.push({ pos: [0, 1, 2].map(j => a[j] + (b[j] - a[j]) * k + gauss() * spread), color, size, region });
    }
  };
  along([0.5, 2.75, 0.25], [0, 2.5, 0], 150, 0.05, rgb(REGION.HA[1]), 13, 0);
  along([0, 2.5, 0], [0, 1.55, 0], 320, 0.05, rgb(REGION.HA[1]), 13, 0);
  function branch(from, dir, length, depth) {
    const to = from.map((v, j) => v + dir[j] * length);
    along(from, to, Math.max(14, 90 - depth * 12), 0.012 + 0.006 * (7 - depth), rgb(REGION.TB[1]), 12 - depth * 0.7, 1);
    const sacs = depth === 7 ? 34 : depth >= 3 ? 26 : 0;
    for (let i = 0; i < sacs; i++) lungPoints.push({ pos: to.map(v => v + gauss() * (0.16 + 0.03 * (7 - depth))), color: rgb(REGION.AL[1]), size: 7.5, region: 2 });
    if (depth === 7) return;
    for (const sign of [-1, 1]) {
      const a = sign * (0.4 + rand(0.1)), c = Math.cos(a), k = Math.sin(a);
      const turn = depth % 2 ? [dir[0], dir[1] * c - dir[2] * k, dir[1] * k + dir[2] * c] : [dir[0] * c - dir[1] * k, dir[0] * k + dir[1] * c, dir[2]];
      turn[1] -= 0.08; turn[0] *= 0.9;
      const norm = Math.hypot(...turn);
      branch(to, turn.map(v => v / norm), length * 0.8, depth + 1);
    }
  }
  along([0, 1.55, 0], [0, 0.95, 0], 160, 0.035, rgb(REGION.TB[1]), 14, 1);
  branch([0, 0.95, 0], [-0.55, -0.83, 0], 0.62, 1);
  branch([0, 0.95, 0], [0.55, -0.83, 0], 0.62, 1);
  const lung = cloud(lungPoints);
  lung.geometry.translate(0, -0.55, 0);

  // ---------- where things sit for each chapter (x, y as share of the visible area) ----------
  const POSES = {
    hero:      { flame: [0.23, 0.0, 1.3, 1], lung: [-0.2, 0, 0.7, 0] },
    lifecycle: { flame: [0.37, 0.3, 0.5, 0.5], lung: [-0.2, 0, 0.7, 0] },
    materials: { flame: [0.44, 0.4, 0.22, 0.12], lung: [-0.2, 0, 0.8, 0] },
    exposure:  { flame: [0.46, 0.42, 0.16, 0.2], lung: [-0.19, -0.05, 0.8, 1] },
    science:   { flame: [0.4, 0.34, 0.34, 0.45], lung: [-0.2, 0, 0.7, 0] },
    simulator: { flame: [-0.2, 0.2, 0.62, 1], lung: [-0.19, -0.05, 0.8, 1] },
    assistant: { flame: [0.4, -0.3, 0.4, 0.3], lung: [0.3, 0.05, 0.85, 0.16] },
  };
  let pose = POSES.hero, pointer = [0, 0], anchor = {};
  const now = { flame: [...pose.flame], lung: [...pose.lung] };
  const levels = new THREE.Vector3(0.3, 0.3, 0.3), levelTarget = levels.clone();
  let grow = 1, vigor = 1, vigorNow = 1;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function resize() {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize);
  addEventListener("pointermove", e => pointer = [e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5]);
  resize();

  function frame(ms) {
    const t = ms / 1000;
    const viewH = 2 * Math.tan(THREE.MathUtils.degToRad(20)) * camera.position.z, viewW = viewH * camera.aspect;
    const narrow = innerWidth < 900;
    for (const [name, mesh] of [["flame", flame], ["lung", lung]]) {
      const target = pose[name], cur = now[name];
      for (let i = 0; i < 4; i++) cur[i] += (target[i] - cur[i]) * 0.06;
      const box = anchor[name] ? anchor[name].getBoundingClientRect() : null;
      if (box) {
        mesh.position.set(((box.left + box.width / 2) / innerWidth - 0.5) * viewW, -((box.top + box.height / 2) / innerHeight - 0.5) * viewH, 0);
        mesh.scale.setScalar(name === "lung" ? Math.min(box.height / innerHeight * viewH / 4.9, box.width / innerWidth * viewW / 4.2) : box.height / innerHeight * viewH / 3.4 * vigorNow);
      } else {
        mesh.position.set((narrow && name === "lung" ? 0 : cur[0]) * viewW, cur[1] * viewH, 0);
        mesh.scale.setScalar(cur[2] * (name === "lung" ? Math.min(1, viewH / 6.4) : Math.min(1.1, viewW / 9) * (pose === POSES.simulator ? vigorNow : 1)));
      }
      mesh.material.uniforms.uOpacity.value = cur[3];
      mesh.visible = cur[3] > 0.01;
    }
    levels.lerp(levelTarget, 0.08);
    vigorNow += (vigor - vigorNow) * 0.06;
    lung.material.uniforms.uLevels.value.copy(levels);
    smoke.material.uniforms.uGrow.value += (grow - smoke.material.uniforms.uGrow.value) * 0.08;
    lung.rotation.y = (still ? 0.35 : Math.sin(t * 0.25) * 0.55) + pointer[0] * 0.5;
    lung.rotation.x = pointer[1] * 0.15;
    flame.rotation.y = still ? 0 : t * 0.12;
    flame.rotation.x = pointer[1] * 0.3;
    for (const mesh of [flame, smoke, lung]) {
      mesh.material.uniforms.uTime.value = still ? 0 : t;
      mesh.material.uniforms.uPx.value = renderer.getPixelRatio() * innerHeight / 900;
    }
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    setPose: (name, section) => { pose = POSES[name] || pose; anchor = { lung: section.querySelector(".lung-space"), flame: section.querySelector(".flame-space") }; },
    setDeposition: f => levelTarget.set(...["HA", "TB", "AL"].map(k => Math.min(1, Math.sqrt(f[k] / 0.3)))),
    setSmokeSize: ratio => grow = ratio,
    setFlame: strength => vigor = strength,
  };
}
let scene3d = { setPose() {}, setDeposition() {}, setSmokeSize() {}, setFlame() {} };
try { scene3d = buildScene(); } catch (error) { report("3D scene is off (this browser has no WebGL); charts and assistant still work", error); }

// ==================== PAGES ====================
function showPage() {
  const id = location.hash.slice(1), page = document.getElementById(id)?.classList.contains("page") ? document.getElementById(id) : $("#top");
  $$(".page").forEach(p => p.hidden = p !== page);
  $$(".rail a[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === page.id));
  scene3d.setPose(page.dataset.scene, page);
  scrollTo(0, 0);
  $$(".js-plotly-plot", page).forEach(plot => Plotly.Plots.resize(plot));
}
addEventListener("hashchange", showPage);
showPage();

// ==================== CHART STYLE ====================
const axis = extra => ({ gridcolor: GRID, linecolor: "rgba(238,240,242,.25)", zeroline: false, ticks: "outside", ticklen: 4, tickcolor: "rgba(238,240,242,.25)", ...extra });
const layout = extra => ({ paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Plex Mono, monospace", size: 11, color: INK2 },
  margin: { l: 64, r: 28, t: 34, b: 48 }, hoverlabel: { bgcolor: "#0d1117", bordercolor: "#3a424e", font: { family: "Plex Mono, monospace", color: INK } },
  legend: { orientation: "h", y: 1.09, x: 0, font: { color: INK2 } }, ...extra });
const draw = (id, traces, lay) => Plotly.react(id, traces, layout(lay), { displayModeBar: false, responsive: true });
const label = (x, y, text, extra = {}) => ({ x, y, text, showarrow: false, font: { color: INK, size: 11 }, yshift: 12, ...extra });

// ==================== 01 LIFECYCLE ====================
const cards = await getJson("/api/cards").catch(e => (report("cards", e), []));
function showStage(stage) {
  $$(".stages button").forEach(b => b.setAttribute("aria-selected", b.dataset.stage === stage));
  $("#cards").innerHTML = cards.filter(c => c.stage === stage).map(c => `
    <article class="card">
      <span class="id">${c.psi_id || "MODEL"}</span>
      <h3>${c.title}</h3>
      <p>${c.what}</p>
      <ul>${c.findings.map(f => `<li>${f}</li>`).join("")}</ul>
      <p class="meaning">${c.safety_meaning}</p>
      <small>${c.sources.join(" · ")}</small>
    </article>`).join("");
}
$$(".stages button").forEach(b => b.onclick = () => showStage(b.dataset.stage));
const COLUMNS = { objective: "Objective", fuel: "Fuel and sample", conditions: "Test conditions", variables: "What varied", measurements: "What was measured", hardware: "Hardware" };
$("#compare").innerHTML = `<tr><th>Investigation</th>${Object.values(COLUMNS).map(c => `<th>${c}</th>`).join("")}</tr>` +
  cards.filter(c => c.compare).map(c => `<tr><td>${c.compare.name}<small>${c.psi_id}</small></td>${Object.keys(COLUMNS).map(k => `<td>${c.compare[k]}</td>`).join("")}</tr>`).join("");
showStage("overheating");

// ==================== 02 MATERIALS ====================
const matrix = await getJson("/api/matrix").catch(e => (report("matrix", e), null));
if (matrix) try {
function fireCell(f) {
  if (!f) return `<td class="gap">NO DATA</td>`;
  const lines = [];
  if (f.bass_tests) {
    const total = Object.values(f.bass_tests).reduce((a, b) => a + b, 0);
    lines.push(`<b>BASS: ${f.bass_tests.burned || 0} of ${total} tests burned</b>`);
  }
  if (f.saffire_samples) lines.push(`Saffire: ${f.saffire_samples} samples` + (f.saffire_ug_burn_length.length ? `, burn length in orbit ${f.saffire_ug_burn_length.join("; ")}` : ""));
  return `<td>${lines.join("")} <small>${f.source}</small></td>`;
}
const smokeCell = s => s ? `<td><b>${sig(s.gmd_um, 2)} µm particles</b>${sig(s.mass_mg_m3, 3)} mg/m³ at the source, ${s.n_runs} runs <small>${s.source}</small></td>` : `<td class="gap">NO DATA</td>`;
const names = Object.keys(matrix.materials).sort((a, b) => Object.keys(matrix.materials[b]).length - Object.keys(matrix.materials[a]).length);
$("#matrix").innerHTML = `<tr><th>Material</th><th>Does it burn in microgravity? <b class="tag measured">Measured</b></th><th>What is its smoke like? <b class="tag measured">Measured</b></th></tr>` +
  names.map(n => `<tr><td>${n}</td>${fireCell(matrix.materials[n].fire)}${smokeCell(matrix.materials[n].smoke)}</tr>`).join("");

function rankBars(id, order, value, format, unit) {
  const names = [...order].reverse(), x = names.map(n => value(matrix.materials[n].smoke));
  draw(id, [{ type: "bar", orientation: "h", y: names, x, width: 0.5, marker: { color: "#3987e5" }, text: x.map(format), textposition: "outside",
    textfont: { color: INK }, cliponaxis: false, hovertemplate: "%{y}: %{text}<extra></extra>" }],
    { barcornerradius: 4, margin: { l: 96, r: 70, t: 8, b: 40 }, showlegend: false, xaxis: axis({ title: { text: unit }, rangemode: "tozero" }), yaxis: axis({ ticks: "", tickfont: { color: INK, size: 12 } }) });
}
rankBars("rank-count", matrix.rank_alveolar_fraction, s => 100 * s.alveolar_fraction_by_count, v => v.toFixed(1) + "%", "% of inhaled particles");
rankBars("rank-mass", matrix.rank_mass_dose, s => s.mass_deposited_ug_per_10min, v => big(v) + " µg", "µg per 10 min");
} catch (error) { report("materials", error); }

// ==================== 03 FLAME SCIENCE ====================
const science = await getJson("/api/flame-science").catch(e => (report("flame science", e), null));
if (science) try {
  const FUEL_COLOR = { Heptane: "#d95926", Methanol: "#3987e5" };
  $("#fuel-tiles").innerHTML = Object.entries(science.fuels).map(([fuel, f]) => `
    <div class="tile"><h4><span class="dot" style="background:${FUEL_COLOR[fuel]}"></span>${fuel}</h4>
      <dl><div><dt>tests</dt><dd>${f.tests}</dd></div>
      <div><dt>flame went out early</dt><dd>${Math.round(100 * f.share_went_out_early)}%</dd></div>
      <div><dt>median burning rate</dt><dd>${f.median_burning_rate_mm2_s.toFixed(2)}<small> mm²/s</small></dd></div>
      <div><dt>fuel left when it went out</dt><dd>${Math.round(100 * f.median_fuel_left)}%</dd></div></dl></div>`).join("");

  const groups = [...science.groups].reverse(), names = groups.map(g => `${g.fuel} · ${g.diluent}`);
  const OUTCOME = { Extinction: ["flame went out early", "#3987e5"], Disruption: ["droplet broke up", "#d95926"], Completion: ["burned all the fuel", "#199e70"] };
  draw("diluent-plot", Object.entries(OUTCOME).map(([key, [name, color]]) => ({
    type: "bar", orientation: "h", name, y: names, x: groups.map(g => 100 * (g.outcomes[key] || 0) / g.tests), marker: { color, line: { color: "#06080c", width: 2 } },
    text: groups.map(g => g.outcomes[key] || ""), textposition: "inside", insidetextanchor: "middle", textfont: { color: "#fff" },
    hovertemplate: `%{y}: %{text} tests ${name} (%{x:.0f}%)<extra></extra>` })),
    { barmode: "stack", bargap: 0.45, margin: { l: 215, r: 28, t: 34, b: 48 }, xaxis: axis({ title: { text: "% of tests in the group (numbers in bars = tests)" }, range: [0, 100] }), yaxis: axis({ ticks: "", tickfont: { color: INK, size: 12 } }) });
  $("#diluent-table").innerHTML = `<table class="matrix compare"><tr><th>Group</th><th>Tests</th><th>Median burning rate</th><th>Median fuel left when the flame went out</th></tr>${
    science.groups.map(g => `<tr><td>${g.fuel} · ${g.diluent}</td><td>${g.tests}</td><td>${g.median_burning_rate_mm2_s.toFixed(2)} mm²/s</td><td>${Math.round(100 * g.median_fuel_left)}%</td></tr>`).join("")}</table>`;

  draw("cool-plot", Object.keys(FUEL_COLOR).map(fuel => {
    const pts = science.extinction_points.filter(p => p.fuel === fuel);
    return { x: pts.map(p => p.d0_mm), y: pts.map(p => p.fuel_left), name: fuel, mode: "markers", marker: { color: FUEL_COLOR[fuel], size: 9, line: { color: "#06080c", width: 2 } },
      text: pts.map(p => `${p.diluent}, ${Math.round(100 * p.o2_frac)}% oxygen`), hovertemplate: `${fuel}, %{x} mm droplet: %{y:.0%} of fuel left<br>%{text}<extra></extra>` };
  }), { xaxis: axis({ title: { text: "droplet diameter at ignition (mm)" } }), yaxis: axis({ tickformat: ".0%", range: [0, 1.05], title: { text: "fuel still unburned" } }) });
  $("#cool-note").textContent = `Each dot is one FLEX test where the visible flame went out. Higher means more fuel left to feed a cool flame or a re-ignition. ${science.notes.fuel_left} ${science.notes.not_in_data}`;

  const soot = [...science.soot].reverse();
  draw("soot-plot", [{ type: "bar", orientation: "h", y: soot.map(r => r.fuel), x: soot.map(r => r.median_smoke_point_mm), width: 0.5, marker: { color: "#3987e5" },
    text: soot.map(r => `${r.median_smoke_point_mm.toFixed(0)} mm · ${r.tests} tests`), textposition: "outside", textfont: { color: INK }, cliponaxis: false, hovertemplate: "%{y}: median %{x:.1f} mm<extra></extra>" }],
    { barcornerradius: 4, showlegend: false, margin: { l: 200, r: 120, t: 8, b: 44 }, xaxis: axis({ title: { text: "median smoke point (mm) · shorter = sootier" }, rangemode: "tozero" }), yaxis: axis({ ticks: "", tickfont: { color: INK, size: 12 } }) });
  $("#soot-note").textContent = `${science.notes.smoke_point} Smoke point also depends on nozzle size and air speed, which differ between tests, so compare medians with care.`;
} catch (error) { report("flame science", error); }

// ==================== 03 CREW EXPOSURE ====================
const state = { material: "Kapton", dilution: "0.01", activity: "rest", gravity: "microgravity", fuel: "Heptane" };
$$(".seg[data-key]").forEach(seg => {
  const key = seg.dataset.key, paint = () => $$("button", seg).forEach(b => b.classList.toggle("on", b.dataset.v === state[key]));
  $$("button", seg).forEach(b => b.onclick = () => { state[key] = b.dataset.v; paint(); key === "fuel" ? loadFlammability() : loadExposure(); });
  paint();
});
$("#minutes").oninput = () => { $("#minutes-out").textContent = $("#minutes").value; loadExposure(); };

async function loadExposure() {
  const e = await post("/api/exposure", { material: state.material, dilution: state.dilution, minutes: $("#minutes").value, activity: state.activity, gravity: state.gravity });
  scene3d.setDeposition(e.fraction_by_count);
  scene3d.setSmokeSize(e.aged_smoke.gmd_um / e.measured_source_smoke.gmd_um);
  $("#regions").innerHTML = Object.entries(REGION).map(([k, [name, color]]) => `
    <li><span class="dot" style="background:${color}"></span><span>${name}</span><b>${pct(e.fraction_by_count[k])}</b>
    <small>of inhaled particles · ${pct(e.fraction_by_mass[k])} of inhaled mass</small></li>`).join("");
  $("#r-count").textContent = big(e.alveolar_particles_per_min);
  $("#r-mass").textContent = sig(e.mass_deposited_ug_per_10min, 3);
  const left = e.aged_smoke.number_conc_per_cm3 / (e.measured_source_smoke.number_conc_per_cm3 * e.inputs.dilution);
  $("#r-aged").textContent = e.inputs.minutes > 0
    ? `After ${e.inputs.minutes} min: particles grew from ${sig(e.measured_source_smoke.gmd_um, 2)} to ${sig(e.aged_smoke.gmd_um, 2)} µm and ${pct(left)} of them are left.`
    : `Fresh smoke: ${sig(e.measured_source_smoke.gmd_um, 2)} µm particles. Move the minutes slider to age it.`;
  const rest = { light: 25 / 7.5, heavy: 50 / 7.5 }[e.inputs.activity];
  $("#r-advice").textContent = rest ? `Resting instead would cut this dose ${rest.toFixed(1)} times, because the dose scales with the air breathed.`
    : e.inputs.dilution > 0.001 ? "Ten times more dilution (ventilation or distance) cuts this dose ten times. Dilution also slows the smoke's aging."
    : "Already at rest and at the highest dilution offered. A mask or leaving the module are the remaining options.";
  $("#r-advice").dataset.level = "out";
  const low = e.band_low_gravity_effect;
  $("#r-band").textContent = low
    ? `Reduced-gravity band: alveoli ${pct(e.fraction_by_count.AL)} to ${pct(low.fraction_by_count.AL)} of particles, ${sig(e.mass_deposited_ug_per_10min, 3)} to ${sig(low.mass_deposited_ug_per_10min, 3)} µg. The lower gravity effect is our assumption (half the calibrated one).`
    : "On Earth the model has no gravity band.";
  $("#r-source").textContent = `Source smoke measured: ${sig(e.measured_source_smoke.gmd_um, 2)} µm, ${big(e.measured_source_smoke.number_conc_per_cm3)} particles/cm³, ${e.measured_source_smoke.n_runs} runs. ${e.sources.join(" · ")}. ${e.limits}`;

  const c = e.curves, at = (key, dp) => c[key][c.dp_um.findIndex(d => d >= dp)];
  const lines = Object.entries(REGION).map(([k, [name, color]]) => ({ x: c.dp_um, y: c[k], name, mode: "lines", line: { color, width: 2 },
    hovertemplate: `${name}: %{y:.1%} at %{x:.3g} µm<extra></extra>` }));
  const smoke = { x: c.dp_um, y: c.smoke_by_count, yaxis: "y2", name: "sizes in this smoke", mode: "lines", fill: "tozeroy", fillcolor: "rgba(238,240,242,.16)",
    line: { color: INK2, width: 1.5 }, hovertemplate: "%{x:.3g} µm<extra>this smoke</extra>" };
  draw("curve", [...lines, smoke], {
    xaxis: axis({ type: "log", dtick: 1, range: [Math.log10(0.005), Math.log10(20)], title: { text: "particle diameter (µm)" }, anchor: "y2" }),
    yaxis: axis({ domain: [0.34, 1], tickformat: ".0%", title: { text: "share deposited" }, rangemode: "tozero" }),
    yaxis2: axis({ domain: [0, 0.2], showticklabels: false, ticks: "", title: { text: "this smoke" }, range: [0, 1.15] }),
    annotations: [label(Math.log10(3), at("HA", 3), "Head airways", { xanchor: "right", xshift: -8, yshift: 0 }), label(Math.log10(0.0065), at("TB", 0.0065), "Bronchi", { xanchor: "left", yshift: 14 }),
      label(Math.log10(0.03), at("AL", 0.03), "Alveoli")],
  });
}

// ==================== 04 FLAMMABILITY MODEL ====================
const SLIDERS = { o2: v => v + "%", co2: v => v + "%", he: v => v + "%", pressure: v => `${v} mmHg · ${(v / 760).toFixed(2)} atm`, d0: v => v + " mm" };
async function loadFlammability() {
  Object.entries(SLIDERS).forEach(([id, show]) => $(`output[data-for=${id}]`).textContent = show($("#" + id).value));
  const f = await post("/api/flammability", { fuel: state.fuel, o2_pct: $("#o2").value, co2_pct: $("#co2").value, he_pct: $("#he").value, pressure_mmhg: $("#pressure").value, d0_mm: $("#d0").value });
  $("#f-out").textContent = Math.round(100 * f.probability_flame_goes_out_early) + "%";
  $("#f-rate").textContent = f.burning_rate_mm2_s.toFixed(2);
  $("#f-band").innerHTML = `mm²/s · likely ${f.burning_rate_band_10_90.map(v => v.toFixed(2)).join(" to ")} <b class="tag modeled">Modeled</b>`;
  $("#f-left").textContent = Math.round(100 * f.fuel_left_when_hot_flame_goes_out) + "%";
  const advice = f.advice, arrow = (v, unit, digits) => Math.abs(v) < 10 ** -digits / 2 ? "no change" : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}${unit}`;
  $("#f-verdict").textContent = advice.verdict.text;
  $("#f-verdict").dataset.level = advice.verdict.level;
  const END = { sustained: "keeps burning", hidden: "goes out, fuel remains", out: "goes out" };
  $("#advice").innerHTML = `<tr><th>Change one thing</th><th>Goes out early</th><th>Burning rate</th><th>Fuel left behind</th><th>Likely ending</th></tr>` +
    advice.options.map(o => `<tr${o.change === advice.best_single_change ? ' class="best"' : ""}><td>${o.change}${o.change === advice.best_single_change ? "<small>most effective</small>" : ""}</td>
      <td>${arrow(100 * o.goes_out_early_change, " pts", 0)}</td><td>${arrow(o.burning_rate_change, " mm²/s", 2)}</td><td>${arrow(100 * o.fuel_left_change, " pts", 0)}</td><td>${END[o.verdict]}</td></tr>`).join("");
  $("#advice-note").textContent = (advice.best_single_change ? "" : "No single change inside the tested range clearly helps. ") + advice.trade_off;
  $("#f-warn").textContent = f.outside_tested_range.length ? "Outside what FLEX tested (" + f.outside_tested_range.join(", ") + "). Treat this prediction as unreliable." : "Inside the conditions FLEX tested.";
  scene3d.setFlame(0.35 + 1.1 * f.burning_rate_mm2_s * (1 - 0.6 * f.probability_flame_goes_out_early));
  const sweep = f.oxygen_sweep, x = sweep.map(r => r.o2_pct), now = +$("#o2").value;
  draw("flam-plot", [
    { x, y: sweep.map(r => r.p_out), name: "chance hot flame goes out early", mode: "lines", line: { color: "#3987e5", width: 2 }, hovertemplate: "%{y:.0%} at %{x}% oxygen<extra>goes out early</extra>" },
    { x, y: sweep.map(r => r.fuel_left), name: "fuel left behind if it does", mode: "lines", line: { color: "#199e70", width: 2, dash: "dot" }, hovertemplate: "%{y:.0%} at %{x}% oxygen<extra>fuel left</extra>" },
    { x: [...x, ...[...x].reverse()], y: [...sweep.map(r => r.band[1]), ...[...sweep].reverse().map(r => r.band[0])], yaxis: "y2", fill: "toself", fillcolor: "rgba(217,89,38,.18)",
      line: { width: 0 }, hoverinfo: "skip", name: "likely range", showlegend: false },
    { x, y: sweep.map(r => r.rate), yaxis: "y2", name: "burning rate", mode: "lines", line: { color: "#d95926", width: 2 }, hovertemplate: "%{y:.2f} mm²/s at %{x}% oxygen<extra>burning rate</extra>" },
  ], {
    xaxis: axis({ title: { text: "oxygen (%)" }, anchor: "y2", range: [12, 34] }),
    yaxis: axis({ domain: [0.58, 1], tickformat: ".0%", range: [0, 1.02], title: { text: "share" } }),
    yaxis2: axis({ domain: [0, 0.42], rangemode: "tozero", title: { text: "burn rate (mm²/s)" } }),
    shapes: [{ type: "line", x0: now, x1: now, yref: "paper", y0: 0, y1: 1, line: { color: INK, width: 1, dash: "dot" } }],
  });
}
Object.keys(SLIDERS).forEach(id => $("#" + id).oninput = () => loadFlammability().catch(e => report("flammability", e)));
$$("#presets button").forEach(b => b.onclick = () => { $("#o2").value = b.dataset.o2; $("#pressure").value = b.dataset.p; $("#co2").value = 0; $("#he").value = 0; loadFlammability(); });

// ==================== 05 ASSISTANT ====================
const escapeHtml = t => t.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const pretty = t => escapeHtml(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
  .replace(/\[(Measured|Modeled|Recommendation)([^\]]*)\]/g, (_, kind, rest) => `<b class="tag ${kind.toLowerCase()}">${kind}</b>${rest ? `<small>${rest.replace(/^[,:\s—-]+/, " ")}</small>` : ""}`);
let history = [];
async function ask(question) {
  if (!question.trim()) return;
  const chat = $("#chat");
  chat.insertAdjacentHTML("beforeend", `<div class="msg q">${escapeHtml(question)}</div><div class="msg a wait">calling tools on NASA data…</div>`);
  const slot = chat.lastElementChild;
  slot.scrollIntoView({ block: "center", behavior: "smooth" });
  const out = await post("/api/chat", { question, history }).catch(e => ({ answer: "Request failed: " + e, tool_calls: [], failed: true }));
  if (!out.failed) history.push({ role: "user", content: question }, { role: "assistant", content: out.answer || "" });
  slot.classList.remove("wait");
  slot.innerHTML = pretty(out.answer || "No answer.") + (out.tool_calls.length ? `<details><summary>${out.tool_calls.length} tool call${out.tool_calls.length > 1 ? "s" : ""}: ${out.tool_calls.map(c => c.tool).join(", ")}</summary>${
    out.tool_calls.map(c => `<pre>${escapeHtml(c.tool + "(" + JSON.stringify(c.args) + ")\n\n" + JSON.stringify(c.result, null, 1).slice(0, 2500))}</pre>`).join("")}</details>` : "");
}
$("#ask").onsubmit = e => { e.preventDefault(); ask($("#question").value); $("#question").value = ""; };
$$(".chips button").forEach(b => b.onclick = () => ask(b.textContent));
$("#new-chat").onclick = () => { history = []; $("#chat").innerHTML = ""; };

loadExposure().catch(e => report("exposure", e));
loadFlammability().catch(e => report("flammability", e));
