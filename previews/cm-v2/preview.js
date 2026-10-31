// Original CM vector artwork; no external assets, libraries, or network requests.
const names = { cat: "貓", cow: "牛" };
const stages = ["幼年", "成長期", "成熟"];
const $ = (id) => document.getElementById(id);
const stageOf = (level) => (level < 5 ? 0 : level < 10 ? 1 : 2);
const scaleOf = (level) => 1 + 0.03 * Math.min(Math.max(level - 1, 0), 20);

function artwork(animal, stage = 0, portrait = false) {
  const cow = animal === "cow";
  const fur = cow ? "#fff5df" : "#edc889";
  const headY = [64, 61, 58][stage];
  const headRadius = [35, 33, 31][stage];
  const ears = cow
    ? '<path d="M39 41 Q14 24 19 48 Q26 57 40 51 M81 41 Q106 24 101 48 Q94 57 80 51" fill="#ac8261"/><path d="M39 36 Q29 21 41 21 L48 37 M72 37 L79 21 Q91 21 81 36" fill="#ebd19b"/>'
    : '<path d="M28 55 L27 21 Q40 24 49 39 M71 39 Q80 24 93 21 L92 55" fill="#edc889"/><path d="M33 42 L33 30 L43 39 M77 39 L87 30 L87 42" fill="#dda28d"/>';
  return `<svg viewBox="0 0 120 140" role="img" aria-label="${names[animal]}${portrait ? "學生角色" : stages[stage] + "吉祥物"}">
    ${portrait ? '<circle cx="60" cy="70" r="57" fill="#e8eddb"/>' : '<ellipse cx="60" cy="130" rx="37" ry="5" fill="#61784d" opacity=".16"/>'}
    <g stroke="#405849" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">
      ${
        !portrait
          ? `<path d="M85 107 Q111 103 102 82" fill="none" stroke="${cow ? "#ac8261" : "#d9ab6b"}" stroke-width="9"/>
      <ellipse cx="60" cy="${[102, 99, 96][stage]}" rx="${[27, 30, 32][stage]}" ry="${[25, 28, 31][stage]}" fill="${fur}"/>
      <ellipse cx="60" cy="104" rx="17" ry="19" fill="${cow ? "#ead5b4" : "#fff0cd"}" stroke="none"/>
      <path class="leg leg-back" d="M38 115 L37 127 Q42 132 49 127 L49 117" fill="${fur}"/><path class="leg" d="M71 117 L71 127 Q78 132 83 127 L82 115" fill="${fur}"/>`
          : ""
      }
      ${ears}<ellipse cx="60" cy="${headY}" rx="${headRadius}" ry="30" fill="${fur}"/>
      ${cow ? `<path d="M36 43 Q55 30 53 58 Q44 66 32 56" fill="#ac8261" stroke="none"/><ellipse cx="60" cy="${headY + 14}" rx="23" ry="14" fill="#e9b7a1"/><path d="M51 ${headY + 12} v2 M69 ${headY + 12} v2"/>` : '<path d="M52 37 L55 47 M65 47 L68 37" stroke="#c59759"/><path d="M22 70 L38 72 M23 79 L38 77 M82 72 L98 70 M82 77 L97 79" stroke-width="2"/>'}
      <path d="M46 ${headY - 3} v3 M74 ${headY - 3} v3" stroke-width="4.5"/>
      <ellipse cx="38" cy="${headY + 7}" rx="6" ry="3" fill="#e3a08d" stroke="none"/><ellipse cx="82" cy="${headY + 7}" rx="6" ry="3" fill="#e3a08d" stroke="none"/>
      ${!cow ? `<path d="M57 ${headY + 9} L60 ${headY + 12} L63 ${headY + 9} Z" fill="#405849"/>` : ""}
      <path class="mouth" d="M54 ${headY + 19} Q60 ${headY + 24} 66 ${headY + 19}" fill="none" stroke-width="2"/>
      ${stage === 1 && !portrait ? '<path d="M43 91 Q60 101 77 91 L66 108 L60 102 L54 108 Z" fill="#b2c68c"/>' : ""}
      ${stage === 2 && !portrait ? '<path d="M39 89 Q60 99 81 89 L73 104 L60 100 L47 104 Z" fill="#729b7b"/><circle cx="60" cy="103" r="5" fill="#f4d38c"/>' : ""}
      <g class="treat"><ellipse cx="60" cy="88" rx="13" ry="8" fill="#bd885b"/><path d="M55 86 h1 M64 90 h1" stroke="#fff0cb"/></g>
      <path class="heart" d="M92 70 C76 57 86 48 92 55 C101 47 109 58 92 70" fill="#df927d" stroke="none"/>
    </g></svg>`;
}

let mode = "idle";
let feedingTimer;
const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
let motionChosen = false;
$("static").checked = motionPreference.matches;
function applyMotion() {
  document.body.classList.toggle("static", $("static").checked);
  document.body.classList.toggle("paused", document.hidden);
  $("motion-status").textContent = $("static").checked
    ? "目前為靜態模式；按「走動」可主動播放動畫。"
    : "動畫已開啟；勾選「靜態模式」可停止。";
}
function playMode(next, message) {
  motionChosen = true;
  $("static").checked = false;
  applyMotion();
  setMode(next, message);
}
function setMode(next, message) {
  clearTimeout(feedingTimer);
  mode = next;
  for (const value of ["idle", "walk", "feed"])
    document.body.classList.toggle(value, value === mode);
  for (const value of ["idle", "walk"])
    $(value).setAttribute("aria-pressed", String(value === mode));
  $("notice").textContent = message;
}
function render() {
  const animal = $("animal").value;
  const level = Number($("level").value);
  $("heading").textContent = `${names[animal]}夥伴`;
  $("growth").textContent =
    `Lv.${level} · ${stages[stageOf(level)]} · ${scaleOf(level).toFixed(2)} 倍`;
  $("size").style.setProperty("--scale", scaleOf(level));
  $("actor").innerHTML = artwork(animal, stageOf(level));
  $("comparison").innerHTML = [1, 5, 10, 21]
    .map(
      (n) =>
        `<div class="sample"><div class="sample-art" style="--scale:${scaleOf(n)}">${artwork(animal, stageOf(n))}</div><p><strong>Lv.${n} · ${stages[stageOf(n)]}</strong><br>${scaleOf(n).toFixed(2)} 倍</p></div>`,
    )
    .join("");
  setMode("idle", "待機中，試試讓夥伴散步。");
}
$("portraits").innerHTML = Object.keys(names)
  .map(
    (animal) =>
      `<div class="portrait">${artwork(animal, 0, true)}<p>${names[animal]}角色</p></div>`,
  )
  .join("");
$("animal").addEventListener("change", render);
$("level").addEventListener("change", render);
$("idle").addEventListener("click", () => playMode("idle", "待機中。"));
$("walk").addEventListener("click", () =>
  playMode("walk", "散步中：小步往返、雙腳交替擺動。"),
);
$("feed").addEventListener("click", () => {
  playMode("feed", "樣本餵食成功：夥伴吃點心！正式點數與經驗值不變。");
  feedingTimer = setTimeout(
    () => setMode("idle", "餵食反應結束，回到待機。"),
    2000,
  );
});
$("fail").addEventListener("click", () =>
  setMode("idle", "樣本餵食失敗：不播放成功反應，數值保持不變。"),
);
$("static").addEventListener("change", () => {
  motionChosen = true;
  applyMotion();
});
motionPreference.addEventListener("change", () => {
  if (!motionChosen) $("static").checked = motionPreference.matches;
  applyMotion();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && mode === "feed") setMode("idle", "已回到待機。");
  applyMotion();
});
render();
applyMotion();
