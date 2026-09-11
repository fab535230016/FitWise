const FIELDS = ["Tujuan latihan", "Frekuensi per minggu",
                "Level pengalaman", "Riwayat cedera"];

const log = document.getElementById("log");

log.addEventListener("click", (event) => {
  const tombol = event.target.closest("button.cite[data-marker]");
  if (tombol) sorotSumber(tombol);
});
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const dot = document.getElementById("dot");
const statusText = document.getElementById("statusText");
const profileEl = document.getElementById("profile");
const progressEl = document.getElementById("progress");
const progressLabel = document.getElementById("progressLabel");

let sessionId = null;
let busy = false;

const EMPTY = "(belum diisi)";

function renderProfile(rows) {
  const data = rows || FIELDS.map(label => ({ label, value: EMPTY }));
  const filled = data.filter(r => r.value !== EMPTY).length;

  progressEl.innerHTML = data
    .map((r, i) => `<div class="seg${i < filled ? " filled" : ""}"></div>`).join("");
  progressLabel.textContent = `${filled} dari ${data.length} informasi terisi`;

  profileEl.innerHTML = data.map(row => {
    const empty = row.value === EMPTY ? " empty" : "";
    return `<div class="field"><span class="k">${escapeHtml(row.label)}</span>` +
           `<span class="v${empty}">${escapeHtml(row.value)}</span></div>`;
  }).join("");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function renderMarkers(text, citations) {
  const map = {};
  (citations || []).forEach(c => { map[c.marker] = c; });
  return escapeHtml(text).replace(/\[S(\d{1,2})\]/g, (whole, n) => {
    const info = map["S" + n];
    if (!info || !info.valid) {
      return `<span class="cite unknown" title="Sumber tidak dikenali"
                    aria-label="Sumber S${n} tidak dikenali">S${n}</span>`;
    }
    const label = escapeHtml(info.source);

    return `<button type="button" class="cite" data-marker="S${n}"
                    title="${label}" aria-label="Lihat sumber S${n}: ${label}"
            >S${n}</button>`;
  });
}

function sorotSumber(tombol) {
  const turn = tombol.closest(".turn");
  if (!turn) return;
  const jejak = turn.querySelector("details.trace");
  if (!jejak) return;

  jejak.open = true;
  const dokumen = jejak.querySelector(
    `.doc[data-marker="${tombol.dataset.marker}"]`
  );
  if (!dokumen) return;

  jejak.querySelectorAll(".doc.disorot").forEach(d => d.classList.remove("disorot"));
  dokumen.classList.add("disorot");
  const kurangiGerak = typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  dokumen.scrollIntoView({ block: "nearest", behavior: kurangiGerak ? "auto" : "smooth" });
  setTimeout(() => dokumen.classList.remove("disorot"), 2200);
}

function addTurn(who, text, kind, citations) {
  const wrap = document.createElement("div");
  wrap.className = "turn " + (kind || (who === "Kamu" ? "user" : "bot"));
  const body = citations ? renderMarkers(text, citations) : escapeHtml(text);
  wrap.innerHTML = `<div class="who">${escapeHtml(who)}</div>` +
                   `<div class="bubble">${body}</div>`;
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

const SARAN = [
  "Kenapa gerakan itu perlu dihindari?",
  "Aku belum paham teknik gerakan yang pertama.",
  "Berapa lama sampai kelihatan hasilnya?",
  "Kalau cuma punya dumbbell gimana?",
  "Perlu pemanasan seperti apa?"
];

function addChips(turn) {
  const label = document.createElement("div");
  label.className = "chips-label";
  label.textContent = "Kamu bisa tanya lanjutan, misalnya:";
  const box = document.createElement("div");
  box.className = "chips";
  SARAN.forEach(teks => {
    const b = document.createElement("button");
    b.className = "chip";
    b.type = "button";
    b.textContent = teks;
    b.addEventListener("click", () => {
      if (busy) return;
      input.value = teks;
      form.requestSubmit();
    });
    box.appendChild(b);
  });
  turn.appendChild(label);
  turn.appendChild(box);
}

function addCopy(turn, text) {
  const b = document.createElement("button");
  b.className = "copy";
  b.type = "button";
  b.textContent = "Salin rencana";
  b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      b.textContent = "Tersalin";
      setTimeout(() => { b.textContent = "Salin rencana"; }, 1800);
    } catch (e) {
      b.textContent = "Gagal menyalin";
    }
  });
  const row = turn.querySelector(".meta-row");
  if (row) row.appendChild(b); else turn.appendChild(b);
}

const GERAKAN_TAMPIL_AWAL = 3;

function tagGerakan(teks, kelas) {
  const el = document.createElement("span");
  el.className = "tag" + (kelas ? " " + kelas : "");
  el.textContent = teks;
  return el;
}

const JEDA_BINGKAI_MS = 1150;
const KURANGI_GERAK = typeof window.matchMedia === "function"
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const pengamatPeraga = "IntersectionObserver" in window
  ? new IntersectionObserver(entri => {
      entri.forEach(e => {
        const kotak = e.target;
        if (!kotak._mulai) return;
        if (e.isIntersecting && !kotak._dijeda) kotak._mulai();
        else kotak._henti(true);
      });
    }, { threshold: 0.35 })
  : null;

function kendaliPeraga(kotak, lapisan, gambar, keterangan) {
  let indeks = 0;
  let pewaktu = null;

  const tombol = document.createElement("button");
  tombol.type = "button";
  tombol.className = "gerakan-putar";

  function tampilkan(i) {
    indeks = i % lapisan.length;
    lapisan.forEach((el, n) => el.classList.toggle("aktif", n === indeks));
    keterangan.textContent = gambar[indeks].keterangan || "";
  }

  function mulai() {
    if (pewaktu) return;
    pewaktu = setInterval(() => tampilkan(indeks + 1), JEDA_BINGKAI_MS);
    tombol.textContent = "Jeda";
    tombol.setAttribute("aria-pressed", "true");
  }

  function henti(sementara) {
    clearInterval(pewaktu);
    pewaktu = null;
    if (sementara) return;
    tombol.textContent = "Putar";
    tombol.setAttribute("aria-pressed", "false");
  }

  tombol.addEventListener("click", () => {
    if (pewaktu) { kotak._dijeda = true; henti(); }
    else { kotak._dijeda = false; mulai(); }
  });

  kotak._mulai = mulai;
  kotak._henti = henti;

  kotak._dijeda = KURANGI_GERAK;
  henti();
  return tombol;
}

function bangunGambar(gerakan) {
  const gambar = gerakan.gambar || [];
  if (!gambar.length) return null;

  const kotak = document.createElement("div");
  kotak.className = "gerakan-gambar";
  const bingkai = document.createElement("div");
  bingkai.className = "gerakan-bingkai";

  const lapisan = [];
  gambar.forEach((item, i) => {
    const foto = document.createElement("img");
    foto.src = item.url;
    foto.alt = `${gerakan.nama} — ${item.keterangan}`;
    foto.loading = "lazy";
    foto.className = "gerakan-bidang" + (i === 0 ? " aktif" : "");
    foto.addEventListener("error", () => {
      foto.remove();
      if (!bingkai.querySelector("img")) kotak.classList.add("gagal");
    });
    bingkai.appendChild(foto);
    lapisan.push(foto);
  });

  const keterangan = document.createElement("figcaption");
  keterangan.className = "gerakan-keterangan";
  keterangan.textContent = gambar[0].keterangan || "";
  bingkai.appendChild(keterangan);
  kotak.appendChild(bingkai);

  if (lapisan.length > 1) {
    kotak.appendChild(kendaliPeraga(kotak, lapisan, gambar, keterangan));
    if (pengamatPeraga) pengamatPeraga.observe(kotak);
  }
  return kotak;
}

function kartuGerakan(gerakan) {
  const kartu = document.createElement("article");
  kartu.className = "gerakan-kartu";

  const gambar = bangunGambar(gerakan);
  if (gambar) kartu.appendChild(gambar);

  const isi = document.createElement("div");
  isi.className = "gerakan-isi";

  const nama = document.createElement("h4");
  nama.textContent = gerakan.nama;
  isi.appendChild(nama);

  if (gerakan.nama_id) {
    const arti = document.createElement("p");
    arti.className = "gerakan-arti";
    arti.textContent = gerakan.nama_id;
    isi.appendChild(arti);
  }

  const disebut = (gerakan.disebut_sebagai || "").toLowerCase();
  if (disebut && disebut !== gerakan.nama.toLowerCase().replace(/-/g, " ")) {
    const rujuk = document.createElement("p");
    rujuk.className = "gerakan-rujuk";
    rujuk.textContent = `Disebut pada rencana sebagai "${gerakan.disebut_sebagai}"`;
    isi.appendChild(rujuk);
  }

  const tag = document.createElement("div");
  tag.className = "gerakan-tag";
  if (gerakan.pola_gerak) tag.appendChild(tagGerakan(gerakan.pola_gerak, "pola"));
  if (gerakan.alat) tag.appendChild(tagGerakan(gerakan.alat));
  (gerakan.kelompok_otot_utama || []).slice(0, 2)
    .forEach(otot => tag.appendChild(tagGerakan(otot)));
  if (tag.childElementCount) isi.appendChild(tag);

  const langkah = gerakan.langkah || [];
  if (langkah.length) {
    const daftar = document.createElement("ol");
    daftar.className = "gerakan-langkah";
    langkah.forEach(baris => {
      const li = document.createElement("li");
      li.textContent = baris;
      daftar.appendChild(li);
    });
    isi.appendChild(daftar);
  }

  if (gerakan.poin_kunci) {
    const kunci = document.createElement("p");
    kunci.className = "gerakan-kunci";
    kunci.innerHTML = "<b>Perhatikan.</b> " + escapeHtml(gerakan.poin_kunci);
    isi.appendChild(kunci);
  }

  kartu.appendChild(isi);
  return kartu;
}

function addGerakan(turn, exercises) {
  if (!exercises || !exercises.length) return;

  const bagian = document.createElement("section");
  bagian.className = "gerakan";

  const kepala = document.createElement("div");
  kepala.className = "gerakan-kepala";
  const judul = document.createElement("h3");
  judul.textContent = "Panduan gerakan";
  const jumlah = document.createElement("span");
  jumlah.className = "gerakan-jumlah";
  jumlah.textContent = `${exercises.length} gerakan`;
  kepala.appendChild(judul);
  kepala.appendChild(jumlah);
  bagian.appendChild(kepala);

  const catatan = document.createElement("p");
  catatan.className = "gerakan-catatan";
  catatan.textContent =
    "Foto dan tata cara di bawah diambil dari katalog gerakan, bukan dari " +
    "model bahasa. Isi rencana di atas tetap bersumber dari literatur ilmiah " +
    "yang penandanya bisa kamu telusuri.";
  bagian.appendChild(catatan);

  const daftar = document.createElement("div");
  daftar.className = "gerakan-daftar";
  const kartu = exercises.map(gerakan => {
    const el = kartuGerakan(gerakan);
    daftar.appendChild(el);
    return el;
  });
  bagian.appendChild(daftar);

  if (kartu.length > GERAKAN_TAMPIL_AWAL) {
    const tersisa = kartu.length - GERAKAN_TAMPIL_AWAL;
    kartu.slice(GERAKAN_TAMPIL_AWAL).forEach(el => el.classList.add("sembunyi"));

    const tombol = document.createElement("button");
    tombol.type = "button";
    tombol.className = "gerakan-lainnya";
    tombol.textContent = `Tampilkan ${tersisa} gerakan lainnya`;
    tombol.addEventListener("click", () => {
      kartu.forEach(el => el.classList.remove("sembunyi"));
      tombol.remove();
    });
    bagian.appendChild(tombol);
  }

  const sumber = (exercises[0] && exercises[0].sumber_media) || {};
  const lisensi = document.createElement("p");
  lisensi.className = "gerakan-lisensi";
  lisensi.textContent =
    `Ilustrasi berasal dari ${sumber.nama || "katalog terbuka"}` +
    (sumber.lisensi ? ` dengan lisensi ${sumber.lisensi}` : "") +
    ". Panduan ini bersifat umum; hentikan latihan bila timbul nyeri dan " +
    "periksakan diri ke tenaga kesehatan.";
  bagian.appendChild(lisensi);

  turn.appendChild(bagian);

  if (!KURANGI_GERAK) {
    kartu.forEach(el => el.classList.add("masuk"));
    requestAnimationFrame(() => {
      kartu.forEach((el, i) => {
        el.style.transitionDelay = Math.min(i * 60, 300) + "ms";
        el.classList.add("tampil");
      });
    });
  }
}

function addMeta(turn, data) {
  const g = data.grounding || {};
  const row = document.createElement("div");
  row.className = "meta-row";
  let html = "";
  if (g.total_sentences) {
    const all = g.marked_sentences === g.total_sentences;
    html += `<span class="pill${all ? "" : " neutral"}">` +
            `${g.marked_sentences}/${g.total_sentences} kalimat bersumber</span>`;
  }
  if (data.revision_attempts) {
    html += `<span class="pill neutral">disusun ulang ${data.revision_attempts}x</span>`;
  }
  if (data.sources && data.sources.length) {
    html += `<span>${data.sources.length} dokumen dipakai</span>`;
  }
  row.innerHTML = html;
  if (html) turn.appendChild(row);
}

function addFeedback(turn, data) {
  const box = document.createElement("div");
  box.className = "feedback";
  box.innerHTML = `
    <div class="q">Menurutmu rencana ini berguna?</div>
    <div class="fb-buttons">
      <button class="fb" data-rating="berguna" type="button">Berguna</button>
      <button class="fb" data-rating="tidak_berguna" type="button">Belum berguna</button>
    </div>
    <div class="fb-reason">
      <input type="text" placeholder="Alasannya (boleh dikosongkan)" maxlength="500">
      <button class="fb" data-send="1" type="button">Kirim</button>
    </div>`;

  let picked = null;
  const reason = box.querySelector(".fb-reason");
  const reasonInput = box.querySelector("input");

  box.querySelectorAll(".fb[data-rating]").forEach(btn => {
    btn.addEventListener("click", () => {
      picked = btn.dataset.rating;
      box.querySelectorAll(".fb[data-rating]")
         .forEach(b => b.classList.remove("picked"));
      btn.classList.add("picked");
      reason.classList.add("show");
      reasonInput.focus();
    });
  });

  async function submit() {
    if (!picked) return;
    try {
      await post("/api/feedback", {
        session_id: sessionId,
        rating: picked,
        reason: reasonInput.value,
        profile: Object.fromEntries((data.profile || []).map(r => [r.label, r.value])),
        sources: data.sources || [],
        plan_excerpt: (data.plan || "").slice(0, 300)
      });
      box.innerHTML = `<div class="fb-done">Terima kasih, masukanmu sudah tercatat.</div>`;
    } catch (e) {
      box.innerHTML = `<div class="q">Gagal mengirim masukan. Coba lagi nanti.</div>`;
    }
  }

  box.querySelector('.fb[data-send]').addEventListener("click", submit);
  reasonInput.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });
  turn.appendChild(box);
}

function addTrace(turn, retrieval) {
  if (!retrieval || !retrieval.length) return;
  const docs = retrieval.map(d => {
    const tag = d.is_core ? "dokumen inti" : "dokumen tambahan";
    const dist = d.best_distance === null
      ? "disertakan tanpa memandang jarak"
      : `jarak terkecil ${String(d.best_distance).replace(".", ",")}`;
    const snippets = (d.hit_previews || [])
      .map(t => `<div class="snippet">${escapeHtml(t)}...</div>`).join("");
    return `<div class="doc" data-marker="${escapeHtml(d.marker)}">
      <div class="doc-head">
        <span class="cite">${escapeHtml(d.marker)}</span>
        <span class="tag">${tag}</span>
        <span class="name">${escapeHtml(d.source)}</span>
      </div>
      <div class="doc-meta">${dist} — ${d.num_hit_chunks} dari ${d.num_chunks}
        potongan masuk peringkat teratas</div>
      ${snippets}
    </div>`;
  }).join("");

  const el = document.createElement("details");
  el.className = "trace";
  el.innerHTML = `<summary>Lihat dokumen yang diambil (${retrieval.length})</summary>` +
                 `<div class="trace-body">${docs}</div>`;
  turn.appendChild(el);
}

function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "turn bot";
  wrap.innerHTML = `<div class="who">FitWise</div>` +
    `<div class="bubble dots"><span></span><span></span><span></span></div>`;
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

const BATAS_WAKTU_MS = 90000;

async function post(url, payload) {

  const pembatal = new AbortController();
  const pewaktu = setTimeout(() => pembatal.abort(), BATAS_WAKTU_MS);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: pembatal.signal
    });
    return { ok: res.ok, data: await res.json() };
  } finally {
    clearTimeout(pewaktu);
  }
}

async function checkHealth() {
  try {
    const data = await (await fetch("/api/health")).json();
    if (data.ready) {
      dot.className = "dot on";
      statusText.textContent = `siap — ${data.chunks} potongan terindeks`;
    } else {
      dot.className = data.error ? "dot off" : "dot";
      statusText.textContent = data.error ? "gagal disiapkan" : "menyiapkan model...";
      if (!data.error) setTimeout(checkHealth, 2500);
    }
  } catch (e) {
    dot.className = "dot off";
    statusText.textContent = "tidak terhubung";
  }
}

function setBusy(value) {
  busy = value;
  send.disabled = value;
  input.disabled = value;
  if (!value) input.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || busy) return;

  addTurn("Kamu", message);
  input.value = "";
  input.style.height = "auto";
  setBusy(true);
  const typing = addTyping();

  try {
    const { ok, data } = await post("/api/chat", { message, session_id: sessionId });
    typing.remove();

    if (data.session_id) sessionId = data.session_id;

    if (!ok) {
      const info = data.filled_fields !== undefined
        ? `\n\nProfilmu masih tersimpan (${data.filled_fields} dari ` +
          `${data.total_fields} terisi). Coba kirim ulang pesanmu.`
        : "";
      addTurn("FitWise", (data.error || "Terjadi kesalahan.") + info, "error");
      if (data.profile) renderProfile(data.profile);
      return;
    }

    renderProfile(data.profile);
    const siap = data.status === "rencana_siap";
    const lanjutan = data.status === "jawaban_lanjutan";
    const body = siap ? data.plan : data.message;
    const turn = addTurn("FitWise", body || "", null,
                         (siap || lanjutan) ? data.citations : null);

    if (lanjutan) {
      addMeta(turn, data);
      addGerakan(turn, data.exercises);
      addTrace(turn, data.retrieval);
    }

    if (siap) {
      addMeta(turn, data);
      addCopy(turn, data.plan || "");
      if (data.compliance && data.compliance.patuh === false) {
        const el = document.createElement("div");
        el.className = "notice";
        el.textContent = "Catatan kepatuhan: " +
          (data.compliance.pelanggaran || []).join(", ");
        turn.appendChild(el);
      }
      addGerakan(turn, data.exercises);
      addTrace(turn, data.retrieval);
      addFeedback(turn, data);
      addChips(turn);
    }

  } catch (e) {
    typing.remove();
    const pesan = e.name === "AbortError"
      ? "Server tidak membalas dalam 90 detik. Rencanamu mungkin masih diproses — " +
        "tunggu sebentar lalu kirim ulang pesanmu."
      : "Gagal menghubungi server. Pastikan server masih jalan, lalu coba lagi.";
    addTurn("FitWise", pesan, "error");
  } finally {
    setBusy(false);
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 130) + "px";
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.getElementById("reset").addEventListener("click", async () => {
  if (busy) return;
  await post("/api/reset", { session_id: sessionId });
  log.innerHTML = "";
  renderProfile(null);
  addTurn("FitWise", "Halo! Kamu mau program latihan seperti apa?");
  input.focus();
});

renderProfile(null);
addTurn("FitWise", "Halo! Kamu mau program latihan seperti apa?");
checkHealth();

document.querySelectorAll('a[href="#chat"]').forEach(a => {
  a.addEventListener("click", () => setTimeout(() => input.focus(), 400));
});

async function muatBasisPengetahuan() {
  const wadah = document.getElementById("sumberDaftar");
  const angka = document.getElementById("angkaKb");
  try {
    const data = await (await fetch("/api/knowledge-base")).json();
    if (!data.documents) throw new Error("belum siap");

    angka.innerHTML = [
      [data.total_documents, "dokumen ilmiah"],
      [data.total_chunks.toLocaleString("id-ID"), "potongan terindeks"],
      [Math.round(data.total_characters / 1000) + "rb", "karakter"],
      ["1024", "dimensi vektor"]
    ].map(([n, l]) =>
      `<div class="kartu"><div class="nilai">${n}</div>` +
      `<div class="label">${l}</div></div>`).join("");

    wadah.innerHTML = data.documents.map(d =>
      `<div class="sumber-baris">
         <span class="kat">${escapeHtml(d.kategori)}` +
      (d.is_core ? ' <span class="inti">inti</span>' : '') + `</span>
         <span class="berkas">${escapeHtml(d.source)}</span>
         <span class="jml">${d.num_chunks} potongan</span>
       </div>`).join("");
  } catch (e) {
    wadah.innerHTML = '<div class="sumber-baris">' +
      '<span class="berkas">Daftar sumber tersedia setelah sistem siap.</span></div>';
  }
}

muatBasisPengetahuan();

(function () {
  var kotak = document.getElementById('mulaiCepat'), isian = document.getElementById('input');
  if (kotak && isian) {
    kotak.addEventListener('click', function (e) {
      var chip = e.target.closest('.mc-chip');
      if (!chip) return;
      isian.value = chip.textContent.trim(); isian.focus(); kotak.classList.add('sembunyi');
    });
  }
  var tautan = document.querySelectorAll('nav .tautan a');
  var bagian = [].map.call(tautan, function (a) { return document.querySelector(a.getAttribute('href')); });
  if (tautan.length && window.IntersectionObserver) {
    var pengamat = new IntersectionObserver(function (masuk) {
      masuk.forEach(function (x) {
        if (!x.isIntersecting) return;
        var i = bagian.indexOf(x.target);
        if (i < 0) return;
        tautan.forEach(function (a) { a.classList.remove('aktif'); });
        tautan[i].classList.add('aktif');
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    bagian.forEach(function (b) { if (b) pengamat.observe(b); });
  }

  var profil = document.getElementById('profile');
  if (profil && window.MutationObserver) {
    new MutationObserver(function () {
      profil.querySelectorAll('.field').forEach(function (f) {
        var v = f.querySelector('.v');
        f.classList.toggle('terisi', !(!v || /belum diisi/i.test(v.textContent)));
      });
      if (kotak && !/belum diisi/i.test(profil.textContent)) kotak.classList.add('sembunyi');
    }).observe(profil, { childList: true, subtree: true, characterData: true });
  }
})();

const SASARAN_MUNCUL = [
  ".hero-inner",
  ".statistik .stat",
  ".judul-bagian",
  "#cara .kartu",
  "#sumber .kartu",
  "#tanya details"
];

const DURASI_ANGKA_MS = 1800;

function animasiAngka(el) {
  const cocok = el.textContent.trim().match(/^([\d.,]+)(.*)$/);
  if (!cocok) return;
  const sasaran = parseFloat(cocok[1].replace(/[.,]/g, ""));
  if (!isFinite(sasaran)) return;

  const akhiran = cocok[2];
  const durasi = DURASI_ANGKA_MS;
  const awal = performance.now();

  function langkah(sekarang) {
    const bagian = Math.min((sekarang - awal) / durasi, 1);

    const mulus = 1 - Math.pow(1 - bagian, 3);
    el.textContent = Math.round(sasaran * mulus) + akhiran;
    if (bagian < 1) requestAnimationFrame(langkah);
  }
  requestAnimationFrame(langkah);
}

let sasaranMuncul = [];

function sembunyikanSasaran() {
  sasaranMuncul = [];
  SASARAN_MUNCUL.forEach(pemilih => {
    document.querySelectorAll(pemilih).forEach(el => sasaranMuncul.push(el));
  });
  if (!sasaranMuncul.length) return;

  if (KURANGI_GERAK || !("IntersectionObserver" in window)) {
    sasaranMuncul.forEach(el => el.classList.add("muncul", "tampil"));
    sasaranMuncul = [];
    return;
  }

  sasaranMuncul.forEach(el => el.classList.add("muncul"));
}

function siapkanMuncul() {
  const elemen = sasaranMuncul;
  if (!elemen.length) return;

  const pengamat = new IntersectionObserver((entri, diri) => {
    entri.forEach(e => {
      if (!e.isIntersecting) return;
      const el = e.target;

      const saudara = [...(el.parentElement ? el.parentElement.children : [])]
        .filter(n => n.classList.contains("muncul"));
      const urutan = Math.max(saudara.indexOf(el), 0);
      el.style.transitionDelay = Math.min(urutan * 70, 280) + "ms";

      el.classList.add("tampil");
      el.querySelectorAll(".stat-angka").forEach(animasiAngka);
      if (el.classList.contains("stat-angka")) animasiAngka(el);
      diri.unobserve(el);
    });
  }, { threshold: 0.18, rootMargin: "0px 0px -40px 0px" });

  elemen.forEach(el => pengamat.observe(el));
}

let munculSudahDisiapkan = false;
function siapkanMunculSekali() {
  if (munculSudahDisiapkan) return;
  munculSudahDisiapkan = true;
  siapkanMuncul();
}

sembunyikanSasaran();

if (document.getElementById("pemuat")) {
  document.addEventListener("fitwise:siap", siapkanMunculSekali, { once: true });

  setTimeout(siapkanMunculSekali, 15000);
} else {
  siapkanMunculSekali();
}

const TAMPIL_PENUH_MS = 1500;
const TAMPIL_SINGKAT_MS = 900;
const PENDEKKAN_SAAT_MUAT_ULANG = true;
const JEDA_PENGAMAN_EKSTRA_MS = 4000;

(function layarPemuatan() {
  const pemuat = document.getElementById("pemuat");
  if (!pemuat) return;

  const bilah = pemuat.querySelector(".pemuat-garis span");
  const keterangan = pemuat.querySelector(".pemuat-teks");

  let pernah = false;
  try {
    pernah = sessionStorage.getItem("fitwise_pemuat") === "1";
    sessionStorage.setItem("fitwise_pemuat", "1");
  } catch (e) {

  }

  const durasi = (PENDEKKAN_SAAT_MUAT_ULANG && pernah)
    ? TAMPIL_SINGKAT_MS
    : TAMPIL_PENUH_MS;

  const awal = performance.now();
  let sudah = false;
  let siapHalaman = false;

  document.body.classList.add("terkunci");

  function gambarBilah(sekarang) {
    if (sudah || !bilah) return;
    const bagian = Math.min((sekarang - awal) / durasi, 1);
    bilah.style.width = (bagian * 100).toFixed(1) + "%";
    if (bagian < 1) requestAnimationFrame(gambarBilah);
  }

  function bukaTirai() {
    if (sudah) return;
    sudah = true;
    if (bilah) bilah.style.width = "100%";

    document.body.classList.remove("terkunci");
    document.dispatchEvent(new CustomEvent("fitwise:siap"));

    pemuat.classList.add("selesai");
    if (!KURANGI_GERAK) {
      document.body.classList.add("zoom-keluar");
      setTimeout(() => document.body.classList.remove("zoom-keluar"), 1000);
    }
    setTimeout(() => pemuat.remove(), 700);
  }

  function cobaBuka() {
    if (sudah || !siapHalaman) return;
    const sisa = durasi - (performance.now() - awal);
    if (sisa > 0) setTimeout(cobaBuka, sisa);
    else bukaTirai();
  }

  if (KURANGI_GERAK) {
    pemuat.remove();
    document.body.classList.remove("terkunci");
    document.dispatchEvent(new CustomEvent("fitwise:siap"));
    return;
  }

  requestAnimationFrame(gambarBilah);

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (!sudah && keterangan) keterangan.textContent = "Menyiapkan tampilan";
    });
  }

  function tandaiSiap() {
    siapHalaman = true;
    if (!sudah && keterangan) keterangan.textContent = "Hampir siap";
    cobaBuka();
  }

  if (document.readyState === "complete") tandaiSiap();
  else window.addEventListener("load", tandaiSiap, { once: true });

  setTimeout(bukaTirai, durasi + JEDA_PENGAMAN_EKSTRA_MS);
})();

(function ukurNav() {
  const bilah = document.querySelector("nav");
  if (!bilah) return;

  function perbarui() {
    document.documentElement.style.setProperty(
      "--tinggi-nav", bilah.offsetHeight + "px"
    );
  }

  perbarui();
  window.addEventListener("resize", perbarui);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(perbarui);
})();

const MEREK_JEDA_HURUF_MS = 42;
const MEREK_TAHAN_TERBUKA_MS = 2600;
const MEREK_TAHAN_TERTUTUP_MS = 1200;

(function animasiMerek() {
  const merek = document.querySelector(".brand");
  if (!merek) return;

  const tanda = merek.querySelector(".tanda");
  const wordmark = merek.querySelector(".wordmark");
  if (!tanda || !wordmark) return;

  const teksAwal = wordmark.firstChild;
  if (teksAwal && teksAwal.nodeType === Node.TEXT_NODE) {
    const kumpulan = document.createDocumentFragment();
    Array.from(teksAwal.textContent).forEach(karakter => {
      const el = document.createElement("span");
      el.className = "huruf";
      el.textContent = karakter;
      kumpulan.appendChild(el);
    });
    wordmark.replaceChild(kumpulan, teksAwal);
  }
  const titik = wordmark.querySelector(".titik");
  if (titik) titik.classList.add("huruf");

  const huruf = Array.from(wordmark.querySelectorAll(".huruf"));

  function ukurLebar() {
    merek.style.setProperty("--lebar-merek", wordmark.offsetWidth + 4 + "px");
  }
  ukurLebar();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(ukurLebar);
  window.addEventListener("resize", ukurLebar);

  if (KURANGI_GERAK) {
    merek.classList.add("terbuka");
    return;
  }

  merek.classList.add("berputar");

  let pewaktu = null;
  let berjalan = false;

  function jadwalkan(fn, ms) {
    clearTimeout(pewaktu);
    pewaktu = setTimeout(fn, ms);
  }

  function buka() {
    tanda.style.transitionDelay = "0ms";
    huruf.forEach((el, i) => {
      el.style.transitionDelay = (220 + i * MEREK_JEDA_HURUF_MS) + "ms";
    });
    merek.classList.add("terbuka");
    jadwalkan(tutup, 220 + huruf.length * MEREK_JEDA_HURUF_MS + MEREK_TAHAN_TERBUKA_MS);
  }

  function tutup() {
    huruf.forEach((el, i) => {
      el.style.transitionDelay = ((huruf.length - 1 - i) * MEREK_JEDA_HURUF_MS) + "ms";
    });
    tanda.style.transitionDelay = (huruf.length * MEREK_JEDA_HURUF_MS + 140) + "ms";
    merek.classList.remove("terbuka");
    jadwalkan(buka, huruf.length * MEREK_JEDA_HURUF_MS + MEREK_TAHAN_TERTUTUP_MS + 300);
  }

  function mulai() {
    if (berjalan) return;
    berjalan = true;
    requestAnimationFrame(buka);
  }

  function henti() {
    berjalan = false;
    clearTimeout(pewaktu);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) henti();
    else mulai();
  });

  if (document.getElementById("pemuat")) {
    document.addEventListener("fitwise:siap", mulai, { once: true });
    setTimeout(mulai, 15000);
  } else {
    mulai();
  }
})();

(function tukarTema() {
  const kotak = Array.from(document.querySelectorAll(".tema-kotak"));
  if (!kotak.length) return;

  const akar = document.documentElement;

  function terapkan(tema) {
    akar.setAttribute("data-tema", tema);
    kotak.forEach(el => {
      el.setAttribute("aria-pressed", el.dataset.tema === tema ? "true" : "false");
    });
  }

  terapkan(akar.getAttribute("data-tema") === "gelap" ? "gelap" : "terang");

  kotak.forEach(el => {
    el.addEventListener("click", () => {
      const tema = el.dataset.tema;
      try { localStorage.setItem("fitwise_tema", tema); } catch (e) {}
      terapkan(tema);
    });
  });
})();