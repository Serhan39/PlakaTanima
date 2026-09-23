# Ucuncu Taraf Bilesenler ve Lisans Notlari

Sertek ALPR, asagidaki acik kaynak bilesenleri kullanir. Her biri kendi
lisansi altinda dagitilir; bu lisanslar ticari/kapali kaynak urunlere
gomulmeye izin verir (hicbiri AGPL/GPL gibi "copyleft" bir lisans degildir).

| Bilesen | Kullanim Amaci | Lisans |
|---|---|---|
| FastAPI | Web API cercevesi | MIT |
| SQLAlchemy | Veritabani ORM | MIT |
| Pydantic | Veri dogrulama | MIT |
| onnxruntime | Model calisma zamani (plaka tespiti) | MIT |
| OpenCV (opencv-python-headless) | Goruntu isleme, demo tespit motoru | Apache-2.0 |
| Tesseract OCR + pytesseract | Karakter tanima (OCR) - varsayilan, cevrimdisi | Apache-2.0 |
| EasyOCR (opsiyonel, requirements-easyocr.txt) | Karakter tanima (OCR) - yuksek dogruluk modu | Apache-2.0 |
| cryptography | Izleme listesi sifreleme (Fernet) | Apache-2.0 / BSD |
| python-jose | JWT oturum yonetimi | MIT |
| passlib | Sifre hash'leme (bcrypt) | BSD |
| uvicorn | ASGI sunucu | BSD |

## Onemli Lisans Notu: YOLO / Ultralytics (AGPL-3.0)

Bu urun, plaka tespiti icin YOLO mimarisinden (ornegin YOLOv8) egitilmis bir
modelin **ONNX formatina donusturulup** `onnxruntime` ile calistirilmasini
varsayar (`app/vision/detector.py::OnnxPlateDetector`). Model egitimi ve
ONNX'e aktarim asamasinda `ultralytics` Python paketi kullanilabilir, ancak
bu paket **AGPL-3.0** lisanslidir.

**Sonuc:** `ultralytics` paketi sadece gelistirme/egitim ortaminda
kullanilmali, urunle birlikte musteriye dagitilan calisma zamanina
(runtime) **dahil edilmemelidir**. Sertek ALPR'nin urun surumu sadece
lisansi izin veren `onnxruntime` + eğitilmis model dosyasini (.onnx)
calistirir; bu, AGPL'nin kaynak kodu acma yukumlulugunu urune tasimaz.

Alternatif olarak:
- Egitim/aktarim isini ustlenen bir yukleniciden **Ultralytics Enterprise
  Lisansi** ile hazir/ozel egitilmis model satin alinabilir, veya
- AGPL disi bir tespit mimarisi (ornegin Apache-2.0 lisansli YOLO-NAS,
  ya da klasik OpenCV tabanli yontemler) tercih edilebilir.

Bu konuda nihai karar, hukuk/uyum ekibiyle teyit edilerek verilmelidir.

### Önerilen Hazır Model: Semihocakli/turkish-plate-recognition-w-yolov8-onnx-to-engine-cpp

`models/plate_detector.onnx` için başlangıç noktası olarak, Türk plakaları
üzerinde eğitilmiş, hazır bir YOLOv8 ONNX modeli öneriyoruz:

- **Kaynak:** https://github.com/Semihocakli/turkish-plate-recognition-w-yolov8-onnx-to-engine-cpp
  (`detection_weights/best.onnx`)
- **Lisans:** Apache-2.0 (ticari kullanıma izin verir, copyleft değildir)
- **Doğrulama:** Girdi/çıktı tensör formatı (`[1,3,640,640]` → `[1,5,8400]`,
  tek sınıf "plaka") `app/vision/detector.py::OnnxPlateDetector` ile
  koddan hiçbir değişiklik gerekmeden doğrudan uyumlu olduğu, ve sentetik
  bir test görüntüsünde (plaka benzeri dikdörtgen bölge) modelin doğru
  konumu yüksek güvenle (conf≈0.90) bulduğu doğrulanmıştır. **Gerçek
  kamera koşullarındaki (açı/mesafe/ışık) doğruluğu bağımsız olarak
  ölçülmemiştir** — kuruluma özel gerçek görüntülerle test edilmesi
  önerilir.
- Bu depo, zaten bu projenin "İlham Alinan Acik Kaynak Projeler"
  bölümünde mimari referans olarak anılıyordu; burada ayrıca somut bir
  model dosyası kaynağı olarak da öneriliyor.

## OCR Motoru ve Cevrimdisi (Offline) Calisma

Varsayilan OCR motoru **Tesseract**'tir (`OCR_ENGINE=tesseract`): Docker
imaji derlenirken apt ile birlikte kurulur (`tesseract-ocr`,
`tesseract-ocr-tur`), hicbir model calisma zamaninda internetten
indirilmez. Bu sayede urun, imaj bir kez (internetli bir ortamda)
derlendikten sonra tamamen internetsiz/air-gapped ortamlarda calisabilir
(bkz. README.md - Internetsiz Kurulum).

Opsiyonel `easyocr` motoru (`OCR_ENGINE=easyocr`, `requirements-easyocr.txt`)
kucuk/gercek dunya plaka kirpmalarinda genelde daha yuksek dogruluk ve daha
anlamli guven puani sunar. Artik Dockerfile'da varsayilan olarak kuruludur
(CPU-only torch wheel ile, ~1.4GB imaj boyutu eklenir) ve model agirliklari
build asamasinda (internet varken) onceden indirilip imaja gomulur - bu
yuzden `OCR_ENGINE=easyocr` secilse bile calisma zamaninda internete
ihtiyac yoktur, air-gapped kurulumlarda da calisir.

## Ilham Alinan Acik Kaynak Projeler

Bu urunun ozellik seti ve mimarisi tasarlanirken asagidaki acik kaynak
projelerin GitHub sayfalarinda yayinlanan ozellik/mimari aciklamalari
incelenmis, kod dogrudan kopyalanmadan kendi mimarimiz sifirdan
yazilmistir:

- **baloglu321/plate_rec** (Apache-2.0) - coklu kamera, sifreli izleme
  listesi, rol tabanli yetkilendirme kavramlari icin ilham kaynagi oldu.
- **Semihocakli/turkish-plate-recognition-w-yolov8-onnx-to-engine-cpp**
  (Apache-2.0) - ONNX tabanli, uretime donuk tespit motoru yaklasimi icin
  referans alindi.

## KVKK / Kisisel Veri Notu

Plaka numaralari ve kamera goruntuleri, 6698 sayili KVKK kapsaminda
kisisel veri sayilabilir. `WatchlistEntry` ve `DetectionLog` tablolarinda
plaka bilgisi Fernet ile sifreli tutulur; yine de kurulum yapilan her
musteri icin aydinlatma metni, saklama suresi politikasi ve gerekiyorsa
VERBIS kaydi musteri/Sertek Bilisim tarafindan ayrica saglanmalidir (bkz.
README.md - KVKK ve Uyumluluk).
