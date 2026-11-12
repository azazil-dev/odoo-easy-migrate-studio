# PRD: niits\_easy\_migrate

**Modul Odoo 17 Community Edition: Import & Migrasi Data Cepat, Aman, dan Bisa Di-undo**

Versi dokumen: 1.0 (Draft) | Tanggal: 10 November 2026 | Pemilik: NIITS

## 1. Ringkasan Produk

niits\_easy\_migrate adalah studio migrasi data untuk Odoo 17 CE. Pengguna cukup menjatuhkan file CSV/XLSX, memetakan kolom secara otomatis, memilih mode dan kecepatan, lalu menjalankan import di latar belakang sambil memantau progresnya secara langsung. Setiap import divalidasi lebih dulu sebelum ada data yang ditulis, dan dapat dibatalkan (undo) dengan satu klik.

Modul mendukung 19 tipe data dalam satu antarmuka, diimpor dalam urutan bernomor sehingga setiap file otomatis menemukan record yang menjadi referensinya. Tersedia paket contoh (sample pack) lengkap sebagai template.

**Masalah yang diselesaikan**

- Import bawaan Odoo lambat untuk data besar, mudah timeout, dan tidak resumable.
- Pesan error sulit dipahami dan baru muncul setelah sebagian data tertulis.
- Tidak ada undo; kesalahan import harus dibersihkan manual.
- Migrasi data transaksional (stok awal, saldo awal, sale/purchase order) memerlukan urutan dan relasi yang rumit.

## 2. Keputusan Scope (hasil konfirmasi)

| Topik | Keputusan | Dampak |
| --- | --- | --- |
| Sumber data v1.0 | File saja (CSV/XLSX) | Konektor URL/API/Database dijadwalkan v1.1+ melalui arsitektur source adapter |
| Engine import | ORM saja | Aman terhadap constraint, compute field, dan hak akses; kecepatan dicapai lewat optimasi ORM (lihat bagian 8) |
| Parallel & background | Mandiri: cron + worker internal | Tanpa dependensi OCA queue\_job |
| Dependensi | Modular: core + modul bridge | Hanya fitur sesuai modul terpasang yang aktif |
| Skala | Hingga 1 juta baris per import | Wajib streaming, chunking, dan checkpoint |

**Catatan penting: Direct-SQL.** Nama fitur utama menyebut Direct-SQL fast engine, tetapi keputusan scope adalah ORM saja. Maka di v1.0 mode Fast dibangun di atas ORM yang dioptimalkan, dan tanda petir pada beberapa tipe data berarti jalur ORM-cepat (batch create besar, tracking dimatikan). Engine dirancang sebagai interface (ImportEngine) agar Direct-SQL dapat ditambahkan sebagai engine opsional di versi berikutnya tanpa mengubah wizard. Hindari memakai kata Direct-SQL pada materi pemasaran v1.0.

## 3. Tujuan dan Non-Tujuan

**Tujuan**

- Import 1 juta baris data master dalam waktu wajar tanpa timeout web.
- Validasi menyeluruh sebelum menulis; hasil validasi bisa diunduh sebagai laporan error.
- Import dapat dilanjutkan (resume) setelah gagal atau server restart.
- Undo satu klik per sesi import.
- Pemetaan kolom otomatis dengan akurasi tinggi.
- Urutan dependensi otomatis untuk 19 tipe data.

**Non-Tujuan (v1.0)**

- Konektor URL, REST API, dan database eksternal.
- Direct-SQL engine.
- Ekspor data atau sinkronisasi dua arah.
- Transformasi data kompleks (scripting bebas) di dalam wizard.
- Dukungan Odoo Enterprise-only (mis. multi-barcode Enterprise, Studio).

## 4. Persona

| Persona | Kebutuhan |
| --- | --- |
| Konsultan / implementator Odoo | Migrasi cepat dari sistem lama, data besar, bisa diulang dan di-undo |
| Admin ERP perusahaan | Import mandiri tanpa keahlian teknis, pesan error jelas |
| Staf finance / gudang | Mengisi saldo awal, stok awal, dan jurnal pembuka dengan template siap pakai |

## 5. Arsitektur Modul

**Pola modular** (pilihan: base + bridge):

| Modul | Depends | Isi |
| --- | --- | --- |
| niits\_easy\_migrate | base, web, mail | Wizard studio, engine, job runner, mapping, validasi, undo, sample pack dasar; tipe data Customers dan Vendors (res.partner) |
| niits\_easy\_migrate\_product | niits\_easy\_migrate, product, uom | UoM Categories, UoM, Product Categories, Products, Packagings |
| niits\_easy\_migrate\_stock | niits\_easy\_migrate\_product, stock | Lots/Serials, Opening Stock, Full Products + Lots + Stock + Expiry (expiry memerlukan product\_expiry, opsional) |
| niits\_easy\_migrate\_account | niits\_easy\_migrate, account | Chart of Accounts, Journals, Taxes, Opening Balances, Journal Entries |
| niits\_easy\_migrate\_sale | niits\_easy\_migrate\_product, sale | Full Sale Orders |
| niits\_easy\_migrate\_purchase | niits\_easy\_migrate\_product, purchase | Full Purchase Orders |
| niits\_easy\_migrate\_pos | niits\_easy\_migrate\_product, point\_of\_sale | POS Categories |

Setiap bridge mendaftarkan tipe datanya ke registry di core, sehingga wizard hanya menampilkan tipe data yang tersedia. Rekomendasi: bila ingin pemasangan sederhana, sediakan meta-modul niits\_easy\_migrate\_all yang meng-install semua bridge.

**Komponen internal**

- **Source Adapter**: v1.0 hanya FileAdapter (CSV, XLSX). Interface disiapkan untuk URL/API/DB.
- **Type Registry**: definisi tiap tipe data (model target, field, kunci unik, dependensi, template).
- **Mapper**: pemetaan kolom otomatis dan manual.
- **Validator**: dry-run penuh tanpa commit.
- **Engine**: ImportEngine (implementasi ORM).
- **Job Runner**: cron + worker internal, checkpoint per batch.
- **Undo Log**: pencatatan record yang dibuat dan diubah.

## 6. Alur Pengguna (Wizard 4 Langkah)

**Langkah 1: Source.** Pengguna memilih tipe data, lalu menjatuhkan file CSV/XLSX (drag and drop). Sistem mendeteksi encoding, delimiter, dan sheet. Tombol Unduh Template tersedia untuk tiap tipe.

**Langkah 2: Columns.** Sistem menampilkan pemetaan otomatis dan pratinjau 20 baris pertama. Pengguna dapat mengubah pemetaan, mengabaikan kolom, dan menyimpan pemetaan sebagai preset.

**Langkah 3: Options.** Pengguna memilih:

- Mode: Create only, Update only, Create or Update (upsert berdasarkan kunci unik).
- Kecepatan: Safe (tracking dan constraint penuh), Balanced, Fast (tracking dimatikan, batch besar).
- Jumlah worker dan ukuran batch (dengan nilai default yang disarankan sistem).
- Perilaku error: berhenti di error pertama, lewati baris error, atau semua-atau-tidak-sama-sekali.

**Langkah 4: Review & Run.** Validasi dijalankan lebih dulu dan menampilkan ringkasan (baris valid, peringatan, error) beserta laporan yang bisa diunduh. Jika lolos, pengguna menekan Run. Import berjalan di latar belakang dengan progress bar langsung, hitungan sukses/gagal, kecepatan baris per detik, dan estimasi waktu selesai. Setelah selesai tersedia tombol Open Records, Download Error Report, dan Undo.

## 7. Kebutuhan Fungsional

**FR-1 Input file**

- Mendukung CSV (UTF-8, UTF-8 BOM, Windows-1252) dan XLSX.
- Ukuran file hingga sekitar 500 MB untuk CSV; pembacaan streaming, tidak memuat seluruh file ke memori.
- File disimpan sebagai attachment sesi import dan dapat dihapus otomatis setelah N hari (konfigurasi).

**FR-2 Smart column mapping**

- Pencocokan berdasarkan nama field teknis, label field (semua bahasa aktif), dan sinonim (mis. Nama, Name, Product Name).
- Pencocokan fuzzy dengan skor kepercayaan; di bawah ambang batas ditandai perlu ditinjau.
- Pemetaan untuk field relasi: kolom dapat berisi nama, kode, external ID, atau ID database; pengguna memilih kunci pencarian.
- Preset pemetaan dapat disimpan dan dipakai ulang per tipe data.
- Pratinjau data hasil konversi (tanggal, angka, boolean, selection) sebelum lanjut.

**FR-3 Validate before you write**

- Dry-run penuh tanpa menulis ke database (transaksi di-rollback), atau validasi statis untuk aturan yang bisa dicek tanpa ORM.
- Pemeriksaan: kolom wajib, tipe data, format tanggal dan angka, nilai selection, referensi yang tidak ditemukan, duplikat kunci unik di dalam file, duplikat terhadap data yang sudah ada, constraint model (SQL dan Python) sejauh dapat dideteksi.
- Setiap error memuat nomor baris, kolom, nilai, dan pesan yang mudah dipahami beserta saran perbaikan.
- Laporan error dapat diunduh sebagai CSV/XLSX berisi baris asli ditambah kolom alasan, sehingga dapat diperbaiki dan diunggah ulang.
- Run diblokir bila ada error, kecuali pengguna memilih lewati baris error.

**FR-4 Parallel & resumable**

- File dipecah menjadi batch; tiap batch diproses sebagai unit pekerjaan dengan transaksi sendiri.
- Beberapa worker memproses batch secara paralel (lihat bagian 9).
- Status tiap batch tersimpan (pending, running, done, failed); setelah crash atau restart, pekerjaan dilanjutkan dari batch yang belum selesai.
- Tombol Pause, Resume, Cancel, dan Retry Failed Batches.

**FR-5 One-click undo**

- Setiap sesi mencatat record yang dibuat (model, ID) dan nilai lama untuk record yang diubah.
- Undo menghapus record yang dibuat dan mengembalikan nilai lama pada record yang diubah, dalam urutan terbalik dari urutan dependensi.
- Jika sebuah record sudah dipakai oleh transaksi lain (mis. produk sudah muncul di invoice), undo melewatinya dan melaporkannya, tidak memaksa penghapusan.
- Dokumen yang sudah diposting (journal entry, stok tervalidasi) di-undo dengan pembalikan yang sesuai (reverse/unpost), sesuai kebijakan per tipe data.
- Undo memerlukan konfirmasi dan dicatat di chatter sesi.

**FR-6 Import any model**

- Selain 19 tipe data bawaan, mode Generic memungkinkan memilih model apa pun (hanya untuk grup admin migrasi) dan memetakan field-nya.
- Mode Generic memakai metadata ir.model dan ir.model.fields untuk membangun mapping, validasi, dan template secara otomatis.
- Model dan field yang diblokir dikelola lewat daftar hitam konfigurasi (mis. res.users password, ir.\* sistem).

**FR-7 Watch it run, live**

- Dashboard progres memakai bus/longpolling Odoo atau polling ringan tiap 1 hingga 2 detik.
- Menampilkan: persentase, baris sukses/gagal/dilewati, baris per detik, estimasi sisa waktu, batch aktif, dan log error bergulir.

**FR-8 Review, open records, undo**

- Setelah selesai: ringkasan hasil, tombol membuka daftar record yang dihasilkan (domain berdasarkan Undo Log), unduh laporan, dan Undo.
- Riwayat semua sesi import dapat dicari, dengan filter berdasarkan tipe data, pengguna, status, dan tanggal.

**FR-9 Complete sample pack**

- Paket contoh berupa file bernomor (01 hingga 19) yang saling konsisten, sehingga dapat diimpor berurutan pada database kosong dan menghasilkan data demo yang utuh.
- Tersedia tombol Download Sample Pack (ZIP) dan Load Sample Pack (mengimpor semua secara berurutan).
- Tiap tipe data juga menyediakan template kosong dengan baris contoh dan lembar petunjuk kolom.

## 8. Engine Import (ORM)

Karena engine dipilih ORM saja, kecepatan dicapai melalui:

- create() multi-record dalam satu panggilan (batch hingga ribuan baris).
- Context flags: tracking\_disable, mail\_create\_nolog, mail\_notrack, no\_reset\_password, import\_file, prefetch\_fields yang dibatasi.
- Pre-resolve referensi: seluruh nilai relasi (kategori, UoM, partner, akun, pajak) di-cache dalam dictionary per worker sehingga tidak ada pencarian per baris.
- Penundaan recompute: menonaktifkan recompute mahal selama batch (mis. parent\_path, stock valuation) bila aman, lalu dijalankan di akhir.
- Commit per batch agar memori dan lock terjaga, dengan invalidate cache setelah tiap batch.
- Mode Safe: tanpa optimasi agresif, semua constraint, onchange default, dan tracking aktif.

**Penanda petunjuk kecepatan (petir)** pada Products, Packagings, Customers, Vendors, dan Lots menandai tipe data volume tinggi yang mendapat jalur Fast yang dioptimalkan.

**Target performa (acuan, mesin 8 vCPU / 16 GB, PostgreSQL lokal):**

| Tipe data | Target mode Fast |
| --- | --- |
| Master sederhana (Customers, Product Categories) | 1.500 hingga 3.000 baris/detik |
| Products (dengan varian sederhana) | 300 hingga 800 baris/detik |
| Transaksi (Sale/Purchase Order, Journal Entry) | 100 hingga 300 dokumen/detik |

Angka ini perlu divalidasi lewat benchmark pada fase pengujian; 1 juta baris master sederhana ditargetkan selesai di bawah 30 menit.

## 9. Parallel dan Background Job (Mandiri)

- **Model data**: niits.migrate.job (sesi) dan niits.migrate.batch (unit kerja).
- **Eksekusi**: ir.cron berjalan tiap menit (konfigurasi) untuk memicu pemrosesan; setiap worker mengklaim batch dengan SELECT ... FOR UPDATE SKIP LOCKED agar tidak ada batch diproses ganda.
- **Paralelisme**: pengguna memilih jumlah worker (default disarankan = min(CPU - 1, 4)); worker dijalankan sebagai thread/proses pekerja yang membuka cursor database sendiri. Hal ini mengikuti batas workers dan limit\_time\_real dari odoo.conf; dokumentasi harus menjelaskan konfigurasi server yang diperlukan.
- **Ketahanan**: heartbeat per batch; batch dengan status running tanpa heartbeat melewati batas waktu dikembalikan ke pending (resume otomatis).
- **Urutan dependensi**: bila dalam satu antrian ada beberapa tipe data (mode Run All), job baru dimulai setelah job dependensinya selesai tanpa error fatal.
- **Kontrol**: Pause, Resume, Cancel; pembatalan menghentikan batch baru tetapi tidak membatalkan batch yang sedang commit.
- **Pembatasan konkurensi**: satu job aktif per tipe data per perusahaan untuk mencegah tabrakan kunci unik.

## 10. 19 Tipe Data dan Urutan Impor

Urutan bernomor di bawah adalah urutan default sample pack. Setiap tipe menyatakan dependensinya, dan wizard memperingatkan bila dependensi belum ada.

| No | Tipe data | Model utama | Kunci unik (default) | Bridge | Catatan |
| --- | --- | --- | --- | --- | --- |
| 1 | UoM Categories | uom.category | name | product |  |
| 2 | Units of Measure | uom.uom | name + kategori | product | Perlu kategori (1) |
| 3 | Product Categories | product.category | complete\_name / external ID | product | Mendukung hierarki parent |
| 4 | POS Categories | pos.category | name | pos | Mendukung hierarki parent |
| 5 | Products (petir) | product.template | default\_code / barcode | product | Kategori (3), UoM (2), POS Category (4) opsional |
| 6 | Packagings / Extra Barcodes (petir) | product.packaging | produk + nama / barcode | product | CE memakai product.packaging; multi-barcode Enterprise tidak didukung |
| 7 | Customers (petir) | res.partner | ref / email / external ID | core | customer\_rank diisi |
| 8 | Vendors (petir) | res.partner | ref / email / external ID | core | supplier\_rank diisi |
| 9 | Lots / Serials (petir) | stock.lot | produk + nama | stock | Produk dengan tracking |
| 10 | Opening Stock | stock.quant | produk + lokasi + lot | stock | Diterapkan sebagai inventory adjustment pada lokasi yang dipilih |
| 11 | Full Products + Lots + Stock + Expiry | beberapa model | sama dengan masing-masing | stock | Satu file gabungan; tanggal kedaluwarsa memerlukan product\_expiry |
| 12 | Chart of Accounts | account.account | code | account | Per perusahaan |
| 13 | Journals | account.journal | code | account | Memerlukan akun default (12) |
| 14 | Taxes | account.tax | name + type\_tax\_use | account | Memerlukan akun pajak (12) |
| 15 | Customer Opening Balances | account.move (opening) | partner + akun + tanggal | account | Memerlukan partner (7), akun (12) |
| 16 | Vendor Opening Balances | account.move (opening) | partner + akun + tanggal | account | Memerlukan partner (8), akun (12) |
| 17 | Journal Entries / Opening GL | account.move | ref / nomor | account | Harus seimbang per entry |
| 18 | Full Sale Orders | sale.order + line | nomor / client\_order\_ref | sale | Header dan line dalam satu file, pengelompokan per nomor |
| 19 | Full Purchase Orders | purchase.order + line | nomor / partner\_ref | purchase | Header dan line dalam satu file, pengelompokan per nomor |

**Aturan khusus**

- **Opening Stock**: memakai mekanisme inventory adjustment bawaan; lokasi dan tanggal efektif dapat dipilih; valuasi memakai biaya dari kolom file atau biaya standar produk.
- **Opening Balances dan Journal Entries**: wajib seimbang (debit = kredit); validasi mengecek tanggal terhadap lock date; entry dapat dibuat sebagai draft atau langsung diposting (opsi).
- **Full Sale/Purchase Orders**: opsi status akhir (draft, confirmed, done); konfirmasi dapat memicu picking dan invoice; default adalah dibuat sebagai draft/confirmed tanpa memicu efek samping, ditandai jelas di wizard.
- **Multi-company**: wizard memilih perusahaan target; semua pencarian referensi dibatasi pada perusahaan tersebut.

## 11. Model Data (Garis Besar)

| Model | Field utama |
| --- | --- |
| niits.migrate.job | name, type\_id, state (draft, validating, ready, running, paused, done, failed, undone), source\_attachment\_id, mapping\_id, mode, engine\_speed, workers, batch\_size, error\_policy, company\_id, total\_rows, done\_rows, failed\_rows, skipped\_rows, started\_at, finished\_at, user\_id |
| niits.migrate.batch | job\_id, sequence, row\_from, row\_to, state, worker\_pid, heartbeat, error\_log |
| niits.migrate.mapping | name, type\_id, line\_ids (kolom sumber, field target, kunci pencarian, transformasi, nilai default) |
| niits.migrate.type | code, name, model, depends\_on, sequence, template, is\_composite |
| niits.migrate.error | job\_id, row\_no, column, value, message, severity |
| niits.migrate.undo.log | job\_id, model, res\_id, action (create/update), old\_values (JSON) |
| niits.migrate.sample | type\_id, file, sequence |

## 12. Keamanan dan Hak Akses

- Grup baru: **Migration User** (menjalankan import tipe bawaan) dan **Migration Manager** (mode Generic, undo, pengaturan, hapus riwayat).
- Import dijalankan dengan hak pengguna yang memulai (bukan sudo penuh); aturan akses record (ir.rule) dan hak model tetap dihormati. Penggunaan sudo hanya untuk operasi internal job.
- Daftar hitam model dan field sensitif pada mode Generic.
- File upload divalidasi (ekstensi, ukuran, deteksi macro XLSX tidak dieksekusi); parsing hanya data.
- Perlindungan injeksi formula: nilai sel yang diawali = + - @ pada laporan error yang diekspor diberi awalan aman.
- Audit: setiap sesi, pemetaan, dan undo tercatat dengan pengguna dan waktu.
- Data pribadi dalam file dihapus otomatis sesuai kebijakan retensi.

## 13. Kebutuhan Non-Fungsional

- **Kompatibilitas**: Odoo 17.0 Community, PostgreSQL 12+, Python 3.10+; XLSX via openpyxl/xlrd bawaan Odoo (tanpa dependensi tambahan), CSV via modul csv standar. Fuzzy matching memakai difflib bawaan Python.
- **Memori**: pembacaan streaming; konsumsi memori per worker tidak melebihi sekitar 512 MB pada batch default.
- **Skalabilitas**: 1 juta baris per sesi; riwayat undo log dipartisi per job dan dapat dibersihkan.
- **Ketahanan**: tidak ada kehilangan progres setelah restart server; idempoten pada retry (upsert berdasarkan kunci unik).
- **Lokalisasi**: UI Bahasa Inggris dengan terjemahan Bahasa Indonesia (id.po) disertakan; format tanggal dan angka dapat dikonfigurasi per sesi.
- **Aksesibilitas dan UX**: responsif, mendukung mode gelap Odoo, pesan error dalam bahasa pengguna.
- **Pengujian**: unit test untuk tiap tipe data, uji beban 1 juta baris, uji resume setelah kill proses, uji undo penuh.

## 14. Desain UI (Garis Besar)

- Menu: Migrasi Data, berisi Studio (wizard), Riwayat Import, Preset Pemetaan, Sample Pack, Konfigurasi.
- Studio berupa tampilan OWL satu halaman dengan stepper 4 langkah, area drag and drop, tabel pratinjau, dan panel progres.
- Kartu tipe data dikelompokkan (Master, Inventory, Accounting, Transaksi) dengan lencana urutan dan petir untuk tipe volume tinggi.
- Status job berwarna: draft, running, done, failed, undone.
- Setiap error dapat diklik untuk menyorot baris dan kolom di pratinjau.

### 14.1 Dashboard (halaman awal menu Migrasi Data)

Dashboard adalah halaman pertama yang dibuka dari menu: bersih, lapang, dan memuat tiga blok utama (KPI, Quick Start, Riwayat terbaru) dari atas ke bawah.

| Zona | Isi | Perilaku |
| --- | --- | --- |
| Header | Logo NIITS, judul Migrasi Data, tombol utama Mulai Import Baru, tombol Unduh Sample Pack | Tombol utama membuka Studio tanpa tipe terpilih |
| KPI ringkas (4 kartu) | Import bulan ini; baris berhasil; tingkat keberhasilan (%); job aktif atau gagal yang perlu tindakan | Klik kartu memfilter Riwayat; angka dihitung dari satu panggilan RPC |
| Quick Start | Grid 19 kartu tipe data, dikelompokkan Master, Inventori, Akuntansi, Transaksi; tiap kartu memuat nomor urutan, ikon, lencana petir untuk tipe volume tinggi | Klik kartu langsung membuka Studio dengan tipe terpilih; kartu yang modul bridge-nya belum terpasang tampil redup dengan petunjuk cara mengaktifkan; ada kotak pencarian cepat |
| Riwayat terbaru | 10 sesi terakhir: tipe, nama file, pengguna, status (lencana warna), baris sukses/gagal, durasi, aksi (Buka, Laporan, Undo) | Job yang sedang berjalan menampilkan progress bar mini yang diperbarui langsung; tautan Lihat semua menuju Riwayat Import |
| Kondisi kosong | Ilustrasi sederhana dan ajakan Muat Sample Pack | Muncul saat belum ada sesi import |

### 14.2 Struktur Menu dan Navigasi

Dashboard menjadi halaman awal, dan Studio 4 langkah berjalan sebagai satu halaman OWL di dalam menu yang sama.

- Menu root Migrasi Data langsung membuka Dashboard.
- Submenu: Dashboard, Studio Import, Riwayat Import, Preset Pemetaan, Sample Pack, Konfigurasi.
- Studio dibuka dari tombol Mulai Import Baru, kartu Quick Start, atau submenu Studio; breadcrumb memungkinkan kembali ke Dashboard.
- Meninggalkan Studio saat job berjalan tidak menghentikan job; job tetap tampil di Dashboard dan dapat dibuka kembali.
- Status langkah Studio (file, pemetaan, opsi) dipertahankan saat pengguna menekan Back atau Next.

### 14.3 Arsitektur Front-end (OWL, Odoo 17)

- **Client action**: `niits_easy_migrate.dashboard` dan `niits_easy_migrate.studio` didaftarkan di registry `actions`; aset dimuat lewat bundle `web.assets_backend`.
- **Komponen**: Dashboard, KpiCard, TypeGrid, TypeCard, JobTable, Studio, Stepper, SourceStep, ColumnsStep, OptionsStep, ReviewRunStep, ProgressPanel, ErrorReport.
- **State dan data**: service OWL `niitsMigrate` menyimpan state sesi aktif; data dibaca lewat service `orm` dan satu endpoint agregat `get_dashboard_data` untuk KPI dan riwayat.
- **Progres langsung**: service `bus` dengan channel per job; jika bus tidak tersedia, polling tiap 2 detik.
- **Unggah file**: drop zone kustom dengan progress unggah dan streaming ke server.
- **Tanpa pustaka eksternal**: tidak ada CDN dan tidak ada framework tambahan; ikon memakai SVG inline atau Font Awesome bawaan Odoo.
- **Terjemahan**: semua teks melalui `_t`, dengan terjemahan Bahasa Indonesia.
- **Isolasi gaya**: semua class berawalan `o_niits_` dan SCSS berada di `static/src` modul agar tidak memengaruhi modul lain.

### 14.4 Branding NIITS

Branding NIITS dipakai penuh (palet dan tipografi sendiri). Palet resmi dan font NIITS belum diberikan, sehingga nilai di bawah menunggu brand guide.

| Token CSS | Peran | Nilai |
| --- | --- | --- |
| --niits-primary | Tombol utama, tautan, kartu aktif | Menunggu brand guide NIITS |
| --niits-primary-soft | Latar kartu terpilih, hover | Menunggu brand guide NIITS |
| --niits-accent | Lencana petir, sorotan | Menunggu brand guide NIITS |
| --niits-success / warning / danger | Status berhasil, peringatan, gagal | Menunggu brand guide NIITS |
| --niits-surface / --niits-bg | Kartu dan latar halaman | Menunggu brand guide NIITS |
| --niits-text / --niits-muted | Teks utama dan teks sekunder | Menunggu brand guide NIITS |
| --niits-font | Keluarga font | Font NIITS (dibundel lokal, woff2), cadangan system-ui |

**Prinsip tampilan bersih dan rapi**

- Grid spasi kelipatan 8 px, ruang putih lega, kartu dengan sudut membulat dan bayangan lembut.
- Maksimal dua ketebalan huruf dan tiga ukuran huruf per halaman.
- Ikon konsisten satu gaya; animasi ringan (transisi hover, progress), tanpa animasi berat.
- Kontras warna memenuhi WCAG AA dan seluruh aksi dapat dijangkau dengan keyboard.
- Tata letak responsif: grid Quick Start 4 kolom di layar lebar, 2 kolom di tablet, 1 kolom di layar sempit.
- Font dibundel lokal (tanpa CDN) dan lisensinya harus mengizinkan distribusi bersama modul OPL-1.
- Dark mode bukan target v1.0 karena Odoo 17 Community tidak menyediakannya bawaan; penggunaan token CSS membuka kemungkinan tersebut nanti.

### 14.5 Kriteria Penerimaan UI

1. Dashboard terbuka kurang dari 1,5 detik dengan 10.000 riwayat sesi.
2. Studio 4 langkah berjalan di satu halaman tanpa muat ulang penuh, dan Back atau Next mempertahankan isian.
3. Pratinjau 20 baris muncul kurang dari 1 detik setelah file selesai diunggah.
4. Progres job diperbarui paling lambat setiap 2 detik.
5. Kartu tipe data yang modul bridge-nya belum terpasang tampil redup dan tidak dapat dijalankan.
6. Seluruh teks dapat diterjemahkan dan tidak ada gaya yang bocor ke halaman Odoo lain.

Dampak jadwal (perkiraan saya): pekerjaan UI bermerek menambah sekitar 1 minggu pada milestone M2; perlu dikonfirmasi setelah brand guide diterima.

## 15. Konfigurasi Sistem

| Parameter | Default |
| --- | --- |
| Ukuran batch default | 500 baris (Fast: 2.000) |
| Jumlah worker default | min(CPU - 1, 4) |
| Interval cron | 1 menit |
| Retensi file sumber | 30 hari |
| Retensi undo log | 90 hari |
| Ambang pemetaan otomatis | 0,80 |
| Batas error sebelum berhenti | 100 |

## 16. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Cron dan worker mandiri tidak cocok dengan batas waktu odoo.conf | Job terpotong | Batch kecil dengan checkpoint, heartbeat, dokumentasi setting workers/limit\_time |
| Kecepatan ORM belum memenuhi ekspektasi "fast" | Kepuasan rendah | Benchmark dini, optimasi cache referensi, arsitektur engine pluggable untuk Direct-SQL di masa depan |
| Undo pada dokumen yang sudah dipakai | Data tidak konsisten | Undo parsial dengan laporan, tidak memaksa penghapusan |
| Perbedaan struktur antar modul bridge | Kompleksitas pemeliharaan | Type Registry deklaratif, tiap bridge terisolasi dan diuji sendiri |
| Stok dan valuasi pada Opening Stock | Nilai persediaan salah | Template menyertakan kolom biaya, validasi, dan pratinjau valuasi |
| Lock date dan periode akuntansi | Jurnal ditolak | Validator memeriksa lock date sebelum run |
| Duplikasi data karena re-run | Data ganda | Mode upsert dan deteksi duplikat |

## 17. Milestone Pengembangan

| Fase | Cakupan | Estimasi |
| --- | --- | --- |
| M1: Fondasi | Core, Type Registry, FileAdapter, model data, grup akses | 2 minggu |
| M2: Wizard dan Mapping | Wizard 4 langkah, smart mapping, preset, pratinjau | 3 minggu |
| M3: Validator dan Engine | Dry-run, engine ORM, laporan error | 3 minggu |
| M4: Job Runner | Batch, worker paralel, resume, pause/cancel, progres live | 3 minggu |
| M5: Tipe data master | Tipe 1 hingga 9 (product, pos, partner, lot) | 3 minggu |
| M6: Stok dan Akuntansi | Tipe 10 hingga 17 | 4 minggu |
| M7: Transaksi | Tipe 18 dan 19 | 2 minggu |
| M8: Undo dan Sample Pack | Undo log, sample pack konsisten 19 file | 2 minggu |
| M9: Hardening | Uji beban 1 juta baris, keamanan, terjemahan id, dokumentasi | 3 minggu |

Total estimasi sekitar 25 minggu untuk satu tim kecil (2 hingga 3 developer); estimasi perlu dikonfirmasi setelah spike teknis pada engine dan job runner.

## 18. Kriteria Penerimaan (Ringkas)

1. Pengguna dapat mengimpor satu file CSV/XLSX untuk tiap dari 19 tipe data melalui wizard 4 langkah.
2. Pemetaan otomatis memetakan kolom pada template resmi dengan akurasi 100% dan pada file bernama bebas dengan akurasi sedikitnya 90% pada set uji.
3. Validasi tidak menulis satu record pun ke database dan melaporkan seluruh error beserta nomor baris.
4. Import 1 juta baris master sederhana selesai tanpa timeout web dan dapat dilanjutkan setelah proses server dihentikan di tengah jalan.
5. Undo mengembalikan database ke kondisi sebelum import untuk record yang belum dipakai, dan melaporkan record yang tidak dapat di-undo.
6. Sample pack 19 file dapat diimpor berurutan pada database baru tanpa error, dan seluruh referensi antar-file terpenuhi.
7. Modul hanya menampilkan tipe data untuk modul Odoo yang terpasang.
8. Pengguna tanpa hak Migration tidak dapat menjalankan import atau mengakses riwayat.

## 19. Keputusan Akhir dan Pertanyaan Terbuka

| Topik | Rekomendasi |
| --- | --- |
| Penamaan fitur Direct-SQL | Diputuskan: gunakan nama Fast engine (ORM) pada v1.0; nama Direct-SQL disimpan untuk engine opsional di versi berikutnya |
| Opening Stock memicu valuasi akuntansi | Default memakai mekanisme inventory adjustment bawaan, tersedia opsi tanggal efektif |
| Status akhir Sale/Purchase Order dan Journal Entry | Diputuskan: default draft, opsi confirmed/posted di wizard; jangan otomatis membuat picking/invoice |
| Retensi undo log | 90 hari, dapat dikonfigurasi |
| Lisensi | Diputuskan: OPL-1 (komersial, dijual melalui Odoo Apps); manifest dan header file memakai lisensi OPL-1 |
| Paket pemasangan | Sediakan meta-modul niits\_easy\_migrate\_all |
