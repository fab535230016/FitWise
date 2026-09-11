// Jalankan: npm install jsdom && node tests/uji_peraga_gerakan.js
// Menguji peraga gerakan (pergantian dua bingkai) pada web/static/app.js.
const fs = require("fs");
let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (e) {
  console.error("Butuh jsdom. Jalankan dulu: npm install jsdom");
  process.exit(2);
}

const berkas = require("path").join(__dirname, "..", "web", "static", "app.js");
const blok = fs.readFileSync(berkas, "utf8");

function ambil(nama) {
  const awal = blok.indexOf(`function ${nama}(`);
  if (awal < 0) throw new Error(`fungsi ${nama} tidak ditemukan`);
  let dalam = 0;
  const i = blok.indexOf("{", awal);
  for (let j = i; j < blok.length; j++) {
    if (blok[j] === "{") dalam++;
    else if (blok[j] === "}" && --dalam === 0) return blok.slice(awal, j + 1);
  }
  throw new Error(`kurung fungsi ${nama} tidak seimbang`);
}

const dom = new JSDOM("<!DOCTYPE html><body></body>", { runScripts: "dangerously" });
const { window } = dom;
const doc = window.document;

const skrip = doc.createElement("script");
skrip.textContent = `
  // Pewaktu dipendekkan supaya pengujian tidak perlu menunggu lama.
  const JEDA_BINGKAI_MS = 30;
  const KURANGI_GERAK = false;
  const pengamatPeraga = null;
  ${ambil("kendaliPeraga")}
  ${ambil("bangunGambar")}
  window.bangunGambar = bangunGambar;
`;
doc.body.appendChild(skrip);

const tunggu = ms => new Promise(r => setTimeout(r, ms));

// Menunggu sampai syarat terpenuhi, bukan menebak berapa milidetik yang pas.
// Pewaktu asli bisa meleset kalau mesin sedang sibuk, dan pengujian yang
// mematok waktu persis akan gagal sesekali tanpa ada yang benar-benar rusak.
async function tungguSampai(syarat, batasMs = 1500) {
  const tenggat = Date.now() + batasMs;
  while (Date.now() < tenggat) {
    if (syarat()) return true;
    await tunggu(10);
  }
  return false;
}
let gagal = 0;
function cek(nama, syarat) {
  if (syarat) console.log("  ok   " + nama);
  else { console.log("  GAGAL " + nama); gagal++; }
}

const contoh = {
  nama: "Deadlift",
  gambar: [
    { url: "/static/gerakan/deadlift/0.jpg", keterangan: "Posisi awal" },
    { url: "/static/gerakan/deadlift/1.jpg", keterangan: "Posisi akhir" }
  ]
};

(async () => {
  const kotak = window.bangunGambar(contoh);
  doc.body.appendChild(kotak);

  const bidang = kotak.querySelectorAll("img.gerakan-bidang");
  const keterangan = kotak.querySelector(".gerakan-keterangan");
  const tombol = kotak.querySelector("button.gerakan-putar");

  cek("dua bingkai ditumpuk dalam satu kotak", bidang.length === 2);
  cek("bingkai pertama aktif di awal",
      bidang[0].classList.contains("aktif") && !bidang[1].classList.contains("aktif"));
  cek("keterangan awal benar", keterangan.textContent === "Posisi awal");
  cek("tombol putar tersedia", !!tombol);
  cek("tombol berlabel Putar saat berhenti",
      tombol.textContent === "Putar" && tombol.getAttribute("aria-pressed") === "false");
  cek("alt gambar menyebut nama gerakan dan posisinya",
      bidang[1].alt.includes("Deadlift") && bidang[1].alt.includes("Posisi akhir"));

  // --- Mulai peraga lewat tombol ---
  tombol.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  cek("tombol berubah jadi Jeda setelah ditekan",
      tombol.textContent === "Jeda" && tombol.getAttribute("aria-pressed") === "true");

  cek("bingkai berpindah ke posisi akhir",
      await tungguSampai(() => bidang[1].classList.contains("aktif")));
  cek("keterangan ikut berpindah", keterangan.textContent === "Posisi akhir");
  cek("hanya satu bingkai aktif dalam satu waktu",
      kotak.querySelectorAll("img.aktif").length === 1);

  cek("peraga berputar kembali ke bingkai awal",
      await tungguSampai(() => bidang[0].classList.contains("aktif")));

  // --- Jeda manual ---
  tombol.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const sebelum = kotak.querySelector("img.aktif").src;
  cek("jeda manual menandai kotak sebagai dijeda", kotak._dijeda === true);
  await tunggu(60);
  cek("bingkai berhenti berganti setelah dijeda",
      kotak.querySelector("img.aktif").src === sebelum);

  // --- Berhenti sementara karena keluar layar ---
  tombol.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  kotak._henti(true);
  cek("berhenti sementara tidak mengubah label tombol", tombol.textContent === "Jeda");
  cek("berhenti sementara tidak menandai dijeda", kotak._dijeda === false);

  // --- Gerakan yang cuma punya satu gambar ---
  const tunggal = window.bangunGambar({
    nama: "Plank", gambar: [{ url: "/x/0.jpg", keterangan: "Posisi tahan" }]
  });
  cek("satu gambar tidak diberi tombol putar",
      !tunggal.querySelector("button.gerakan-putar"));

  cek("gerakan tanpa gambar tidak menghasilkan kotak",
      window.bangunGambar({ nama: "Kosong", gambar: [] }) === null);

  // --- Semua gambar gagal dimuat ---
  const rusak = window.bangunGambar(contoh);
  rusak.querySelectorAll("img").forEach(g => g.dispatchEvent(new window.Event("error")));
  cek("kotak disembunyikan kalau semua gambar gagal dimuat",
      rusak.classList.contains("gagal"));

  console.log(gagal === 0 ? "\nSemua lolos." : `\n${gagal} gagal.`);
  process.exit(gagal === 0 ? 0 : 1);
})();
