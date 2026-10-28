# Laporan Eksekutif — Simulasi Pengawasan Distribusi BBM Bersubsidi
*Periode pelaporan: 2026-07-01 s.d. 2026-09-28 · dibuat otomatis 27 October 2026*

## Ringkasan Eksekutif
Dari **400 SPBU** yang diawasi 98 verifikator selama 90 hari, **32 SPBU (8,0%) terindikasi penyimpangan** — terkonsentrasi di **Jawa Timur**. Potensi volume bersubsidi yang tidak tercatat diperkirakan **4.493.841 liter (≈ Rp 35.949.551.789 pada harga bersubsidi)** selama periode pelaporan. Rekomendasi utama: inspeksi ulang prioritas dan penguatan kualitas pelaporan verifikator.

## Kualitas Data & Pelaporan Verifikator
- Laporan diterima 74,160 baris; 2,160 duplikat dihapus, 1,419 salah satuan dikoreksi, 1,760 nilai penjualan kosong.
- Keterlambatan pelaporan 7,9% (5,659 laporan).
- Skor reliabilitas verifikator: rata-rata 0.932, 98/98 di atas ambang 0.70.

### Verifikator dengan skor terendah (kandidat pembinaan)

| Verifikator | Reliabilitas | Kelengkapan | Kiriman ganda | Salah satuan |
|---|---|---|---|---|
| VER-053 | 0.799 | 0.933 | 2,7% | 1,7% |
| VER-073 | 0.846 | 0.939 | 3,4% | 3,0% |
| VER-078 | 0.866 | 0.929 | 2,4% | 1,7% |
| VER-012 | 0.868 | 0.929 | 2,2% | 2,1% |
| VER-007 | 0.873 | 0.949 | 4,3% | 2,8% |

## Temuan Anomali Distribusi
- **32 SPBU terindikasi penyimpangan** (≥2 dari 4 aturan: utilitas kuota rendah, pola penjualan flat, klaim stok habis, melebihi kuota).
- Wilayah dengan temuan terbanyak: Jawa Timur (16), Jawa Tengah (10), Jawa Barat (3).
- Kinerja deteksi terhadap ground truth simulasi — rule-based: presisi 100,0%, recall 100,0%; Isolation Forest: presisi 80,0%, recall 100,0%.

### SPBU prioritas inspeksi ulang (utilitas kuota terendah)

| SPBU | Wilayah | Produk | Utilitas kuota | CV penjualan | Klaim stok habis |
|---|---|---|---|---|---|
| SPBU-0347 | Jawa Timur | Premium | 34,8% | 1,7% | 95,4% |
| SPBU-0092 | Jawa Tengah | Solar | 34,9% | 2,0% | 96,6% |
| SPBU-0247 | Jawa Timur | Solar | 34,9% | 1,9% | 97,7% |
| SPBU-0244 | Jawa Timur | Solar | 34,9% | 2,0% | 100,0% |
| SPBU-0069 | DI Yogyakarta | Premium | 34,9% | 1,9% | 98,9% |
| SPBU-0271 | Jawa Tengah | Solar | 34,9% | 2,0% | 96,6% |
| SPBU-0147 | Jawa Tengah | Premium | 34,9% | 1,8% | 97,7% |
| SPBU-0153 | Jawa Timur | Solar | 34,9% | 1,8% | 92,2% |

## Rekomendasi Tindak Lanjut
1. Inspeksi ulang prioritas 32 SPBU terindikasi penyimpangan, dengan konsentrasi tertinggi di Jawa Timur (16 SPBU).
2. Terapkan rotasi verifikator untuk SPBU dengan skor reliabilitas di bawah 70,0% dan wajibkan pelatihan pengisian form.
3. Aktifkan pemantauan otomatis utilitas kuota harian dengan ambang 60,0%–110,0% agar penyimpangan terdeteksi sebelum akhir periode pelaporan.
4. Verifikasi fisik ketersediaan stok pada SPBU dengan rasio klaim stok habis tinggi namun penjualan rendah (indikasi distribusi tidak sesuai peruntukan).

---
*Catatan metodologi: seluruh data adalah simulasi dengan ground truth yang ditanamkan (parameter di `src/config.py`); business logic mengacu pada pemberitaan publik BPH Migas/Pertamina. Angka pada laporan ini bukan data resmi.*