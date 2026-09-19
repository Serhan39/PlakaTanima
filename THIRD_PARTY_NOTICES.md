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

## OCR Motoru ve Cevrimdisi (Offline) Calisma

Varsayilan OCR motoru **Tesseract**'tir (`OCR_ENGINE=tesseract`): Docker
imaji derlenirken apt ile birlikte kurulur (`tesseract-ocr`,
`tesseract-ocr-tur`), hicbir model calisma zamaninda internetten
indirilmez. Bu sayede urun, imaj bir kez (internetli bir ortamda)
derlendikten sonra tamamen internetsiz/air-gapped ortamlarda calisabilir
(bkz. README.md - Internetsiz Kurulum).

Opsiyonel `easyocr` motoru (`OCR_ENGINE=easyocr`,
`requirements-easyocr.txt`) daha yuksek dogruluk sunabilir ancak ilk
calistirmada model agirliklarini internetten indirir; internetsiz
kurulumlarda kullanilmamali, ya da model Docker imaji build asamasinda
(internet varken) onceden indirilip imaja gomulmelidir.

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
