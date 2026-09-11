// Jalankan: npm install jsdom && node tests/uji_layar_pemuatan.js
// Menguji kontrak layar pemuatan pada web/static/app.js:
// gulir terkunci selama tirai menutup, dan sinyal "fitwise:siap" dikirim tepat
// sekali saat tirai dibuka. Sinyal itulah yang menahan animasi kemunculan
// supaya tidak berjalan di balik tirai.
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

const tunggu = ms => new Promise(r => setTimeout(r, ms));
let gagal = 0;
function cek(nama, syarat) {
  if (syarat) console.log("  ok   " + nama);
  else { console.log("  GAGAL " + nama); gagal++; }
}

function siapkan({ kurangiGerak = false, penuh = 120 } = {}) {
  const dom = new JSDOM(`<!DOCTYPE html><body>
    <div id="pemuat"><div class="pemuat-isi">
      <div class="pemuat-garis"><span></span></div>
      <div class="pemuat-teks">Menyiapkan basis literatur</div>
    </div></div>
  </body>`, { runScripts: "dangerously", pretendToBeVisual: true });

  const skrip = dom.window.document.createElement("script");
  skrip.textContent = `
    // Durasi dipendekkan supaya pengujian tidak menunggu lima detik.
    const TAMPIL_PENUH_MS = ${penuh};
    const TAMPIL_SINGKAT_MS = ${penuh};
    const PENDEKKAN_SAAT_MUAT_ULANG = false;
    const JEDA_PENGAMAN_EKSTRA_MS = 400;
    const KURANGI_GERAK = ${kurangiGerak};
    window.jumlahSinyal = 0;
    document.addEventListener("fitwise:siap", () => { window.jumlahSinyal += 1; });
    ${ambil("layarPemuatan")}
    layarPemuatan();
  `;
  dom.window.document.body.appendChild(skrip);
  return dom;
}

(async () => {
  // --- Jalur normal ---
  const dom = siapkan();
  const w = dom.window;
  const d = w.document;

  cek("gulir terkunci selama tirai menutup",
      d.body.classList.contains("terkunci"));
  cek("belum ada sinyal siap sebelum tirai dibuka", w.jumlahSinyal === 0);
  cek("tirai masih ada di halaman", !!d.getElementById("pemuat"));

  // Halaman selesai dimuat, tapi durasi tahan belum lewat.
  w.dispatchEvent(new w.Event("load"));
  cek("sinyal belum dikirim walau halaman sudah siap, karena tahan belum lewat",
      w.jumlahSinyal === 0);

  await tunggu(260);
  cek("sinyal siap dikirim setelah tahan lewat", w.jumlahSinyal === 1);
  cek("gulir dibuka kembali", !d.body.classList.contains("terkunci"));
  cek("tirai diberi kelas selesai",
      d.getElementById("pemuat") === null
      || d.getElementById("pemuat").classList.contains("selesai"));

  await tunggu(700);
  cek("sinyal tidak dikirim dua kali", w.jumlahSinyal === 1);

  // --- Jalur kurangi gerak ---
  const dom2 = siapkan({ kurangiGerak: true });
  const w2 = dom2.window;
  cek("mode kurangi gerak langsung melepas tirai",
      w2.document.getElementById("pemuat") === null);
  cek("mode kurangi gerak tetap mengirim sinyal siap", w2.jumlahSinyal === 1);
  cek("mode kurangi gerak tidak meninggalkan gulir terkunci",
      !w2.document.body.classList.contains("terkunci"));

  // --- Pengaman: halaman tidak pernah selesai dimuat ---
  const dom3 = siapkan({ penuh: 100 });
  const w3 = dom3.window;
  await tunggu(700);
  cek("tirai tetap terbuka lewat pengaman walau sinyal load tak pernah datang",
      w3.jumlahSinyal === 1);
  cek("pengaman juga membuka kunci gulir",
      !w3.document.body.classList.contains("terkunci"));

  console.log(gagal === 0 ? "\nSemua lolos." : `\n${gagal} gagal.`);
  process.exit(gagal === 0 ? 0 : 1);
})();
