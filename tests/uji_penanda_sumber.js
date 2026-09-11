// Uji perilaku penanda sumber pada index.html memakai jsdom.
// Jalankan: npm install jsdom && node tests/uji_penanda_sumber.js
// Uji ini terpisah dari pytest karena menguji perilaku DOM, bukan kode Python.
const fs = require("fs");
let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (e) {
  console.error("Butuh jsdom. Jalankan dulu: npm install jsdom");
  process.exit(2);
}

const berkas = require("path").join(__dirname, "..", "web", "static", "app.js");
// Ambil hanya fungsi yang diuji, tanpa menjalankan skrip halaman penuh
// (skrip itu memanggil fetch ke server yang tidak ada di lingkungan uji).
const blok = fs.readFileSync(berkas, "utf8");
function ambil(nama) {
  const awal = blok.indexOf(`function ${nama}(`);
  if (awal < 0) throw new Error(`fungsi ${nama} tidak ditemukan`);
  let i = blok.indexOf("{", awal), dalam = 0;
  for (let j = i; j < blok.length; j++) {
    if (blok[j] === "{") dalam++;
    else if (blok[j] === "}" && --dalam === 0) return blok.slice(awal, j + 1);
  }
  throw new Error(`kurung fungsi ${nama} tidak seimbang`);
}

const dom = new JSDOM(`<!DOCTYPE html><body>
  <div id="log" role="log" aria-live="polite"></div>
</body>`, { pretendToBeVisual: true, runScripts: "dangerously" });

const { window } = dom;
global.window = window;
global.document = window.document;
window.Element.prototype.scrollIntoView = function () { this.dataset.digulir = "ya"; };

const konteks = [ambil("escapeHtml"), ambil("renderMarkers"), ambil("sorotSumber")].join("\n");
const skrip = window.document.createElement("script");
skrip.textContent = konteks + `
  window.renderMarkers = renderMarkers;
  window.sorotSumber = sorotSumber;
  const log = document.getElementById("log");
  log.addEventListener("click", (event) => {
    const tombol = event.target.closest("button.cite[data-marker]");
    if (tombol) sorotSumber(tombol);
  });
`;
window.document.body.appendChild(skrip);

const doc = window.document;
let gagal = 0;
function cek(nama, syarat) {
  if (syarat) console.log("  ok   " + nama);
  else { console.log("  GAGAL " + nama); gagal++; }
}

// --- Susun satu giliran percakapan lengkap: teks + panel jejak ---
const citations = [
  { marker: "S1", number: 1, source: "acsm_guidelines.pdf", valid: true },
  { marker: "S2", number: 2, source: "cedera_bahu.pdf", valid: true },
  { marker: "S7", number: 7, source: null, valid: false }
];
const teks = "Latih dua kali seminggu [S1]. Hindari overhead press [S2]. Klaim tanpa dasar [S7].";

const turn = doc.createElement("div");
turn.className = "turn bot";
turn.innerHTML = `<div class="bubble">${window.renderMarkers(teks, citations)}</div>`;
const jejak = doc.createElement("details");
jejak.className = "trace";
jejak.innerHTML = `<summary>Lihat dokumen</summary><div class="trace-body">
  <div class="doc" data-marker="S1"><div class="snippet">isi acsm</div></div>
  <div class="doc" data-marker="S2"><div class="snippet">isi cedera</div></div>
</div>`;
turn.appendChild(jejak);
doc.getElementById("log").appendChild(turn);

// --- Pemeriksaan ---
const tombolS1 = turn.querySelector('button.cite[data-marker="S1"]');
cek("penanda sah dirender sebagai <button>", !!tombolS1);
cek("tombol punya aria-label berisi nama berkas",
    tombolS1 && tombolS1.getAttribute("aria-label").includes("acsm_guidelines.pdf"));

const s7 = turn.querySelector(".cite.unknown");
cek("penanda tak dikenal tetap <span>, bukan tombol", s7 && s7.tagName === "SPAN");
cek("penanda tak dikenal tidak bisa diklik",
    !turn.querySelector('button.cite[data-marker="S7"]'));

cek("panel jejak awalnya tertutup", jejak.open === false);

tombolS1.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
const docS1 = jejak.querySelector('.doc[data-marker="S1"]');
cek("klik membuka panel jejak", jejak.open === true);
cek("dokumen yang cocok disorot", docS1.classList.contains("disorot"));
cek("dokumen yang cocok digulir ke tampilan", docS1.dataset.digulir === "ya");
cek("dokumen lain tidak ikut disorot",
    !jejak.querySelector('.doc[data-marker="S2"]').classList.contains("disorot"));

turn.querySelector('button.cite[data-marker="S2"]')
    .dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
cek("sorotan berpindah ke S2",
    jejak.querySelector('.doc[data-marker="S2"]').classList.contains("disorot"));
cek("sorotan lama pada S1 dilepas", !docS1.classList.contains("disorot"));

// XSS: nama berkas berbahaya tidak boleh lolos ke HTML
const jahat = [{ marker: "S1", source: '"><img src=x onerror=alert(1)>', valid: true }];
const keluaran = window.renderMarkers("Uji [S1].", jahat);
cek("nama sumber berbahaya di-escape", !keluaran.includes("<img"));

console.log(gagal === 0 ? "\nSemua lolos." : `\n${gagal} gagal.`);
process.exit(gagal === 0 ? 0 : 1);
