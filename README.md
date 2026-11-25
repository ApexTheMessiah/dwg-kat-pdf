# DWG Kat PDF

Okul data çizimlerinden (DWG) kat kat PDF çıkarır, data ucu olmayan odaları listeler ve kat bazında uç (port) raporu hazırlar.

## Kurulum

1. **ODA File Converter'ı kurun** (ücretsiz, bir kez): <https://www.opendesign.com/guestfiles/oda_file_converter>
   Program DWG dosyalarını bununla okur. Varsayılan klasöre kurun (`C:\Program Files\ODA\...`).
2. **Programı indirin:** bu sayfanın sağındaki **Releases** bölümünden en son sürümdeki `DWG.Kat.PDF.exe` dosyasını indirin.
3. Dosyaya çift tıklayın. Kurulum yok; istediğiniz klasörde durabilir.

İlk açılışta Windows "Windows kişisel bilgisayarınızı korudu" uyarısı verebilir (program imzalı değil).
**Ek bilgi → Yine de çalıştır** deyin. Kurum bilgisayarında engellenirse bilgi işlem biriminden izin gerekir.

Program ilk açılışta birkaç saniye bekletebilir.

## Kullanım

| Düğme | Ne yapar |
|---|---|
| **Browse…** | Bir ya da birkaç DWG seçer (Ctrl / Shift ile çoklu seçim). Yeni bir liste başlatır. |
| **Folder…** | Bir klasördeki ve alt klasörlerindeki bütün çizimleri listeye ekler. Tekrar basarak başka klasör eklenir. |
| **Run** | Seçilen her çizim için PDF, eksik uç listesi ve port raporu üretir. |
| **Open folder** | Çıktı klasörünü açar. |
| **Port report…** | Yalnızca port raporunu üretir, PDF çizmez. DWG seçin (AutoCAD'den basılmış PDF de olur). |

Uyarılar pencerede kırmızı yazılır.

## Çıktılar

Her şey `İndirilenler\DWG Kat PDF\` (`Downloads\DWG Kat PDF\`) altına yazılır:

- `pdf\<çizim adı>\<çizim adı>.pdf`: kapak sayfası, ardından her kat için bir sayfa (A4).
- `pdf\<çizim adı>\<çizim adı> - eksik data.txt`: data ucu olmayan odalar.
- `port pdf\<çizim adı> - port raporu.txt`: kat kat uç sayıları.
- `port pdf\Port Raporu.docx`: son çalıştırmadaki bütün okulların Word raporu.

Aynı çizim yeniden çalıştırılırsa eski çıktıların üzerine yazılır. `Port Raporu.docx` Word'de açıkken yazılamaz; önce kapatın.

### Port raporu nasıl okunur

```
ZEMİN KAT: 19A 11B  (AP 2: B-01 B-02; PD 1)
TOPLAM: 54A  (AP 3; PD 1)  = 54 uç
```

- `19A 11B`: o katta A kabinetine 19, B kabinetine 11 uç bağlı.
- `AP 2: B-01 B-02`: katta 2 access point var; yanlarında yazan portlar B-01 ve B-02. Access point'in portu 1 uç ve 1 AP sayılır.
- `PD`: proje dışı uç. AP ve PD uç toplamına girmez.
- `UYARI`: tekrar eden ya da atlanan numaralar, etiketsiz uç sembolü, kapaktaki "Toplam Uç Sayısı" ile sayılan arasındaki fark.
- `OLASI NEDEN`: kapak ile sayım farklıysa çizimde bulunan olası açıklamalar. Bunlar tahmindir.

## Çizim nasıl olmalı

Program şu şablonu bekler. Ad farklıysa sayım eksik ya da boş çıkar.

- Tek DWG içinde: `Kapak` katmanında kapak tablosu ve her kat kapalı bir çerçeve içinde. Çerçevede "OKUL ADI - ZEMİN KAT" gibi bir başlık bulunur.
- Katmanlar: `data` (uç blokları), `Yazı-Uc` (uç etiketleri), `Yazı` / `DUVAR` (oda adları), `Kapı`, `Merdiven`.
- Uç etiketleri `A-12` biçiminde yazılır (`A - 12` ve `1A-20` de olur). `A12` ya da `A06` sayılmaz.
- Bloklar: access point için `access point`, proje dışı uç için `planlanan data`.

Katman ve blok adları `dwg_kat_pdf.py` dosyasının başındaki sabitlerdir.

## Sık karşılaşılanlar

- **"ODA File Converter not found"**: 1. adımdaki program kurulu değil ya da başka klasöre kurulmuş.
- **Port report… "no outlet labels can be read in this PDF" diyor**: seçilen PDF bu programın ürettiği PDF'tir (yazıları çizgi olarak çizilir). PDF yerine DWG'yi seçin.
- **Bir odada uç var ama "data ucu yok" deniyor**: oda duvarları kapalı değilse ya da uç duvarın dışında kalıyorsa olur. Uyarının sonunda "duvarın hemen dışında" notu varsa uç oradadır.

## Güncelleme

Yeni sürüm çıktığında **Releases** sayfasından yeni `DWG.Kat.PDF.exe` dosyasını indirip eskisinin yerine koyun.

## Kaynaktan çalıştırma (isteğe bağlı)

Python 3.13 ve ODA File Converter kuruluyken:

```
pip install -r requirements.txt
pythonw dwg_kat_pdf_app.pyw
python dwg_kat_pdf.py --test
```
