# Sertek ALPR — Plaka Tanıma ve Erişim Kontrol Platformu

Sertek Bilişim'in satabileceği, Türkiye plaka formatına özel, yerinde
kurulum (on-premise) plaka tanıma ve erişim kontrol ürünü. Otopark, site,
AVM, fabrika/OSB girişleri gibi senaryolarda çoklu kamera ile plaka
tespiti yapar, izleme listesine (izinli / personel / aranan / kara liste)
göre karşılaştırır ve web panelinden canlı takip sağlar.

Bu depo, GitHub üzerindeki açık kaynak Türk plaka tanıma projeleri
araştırılıp lisans durumları incelendikten sonra **sıfırdan, ticari
kullanıma uygun ve dağıtılabilir** bir mimariyle yazılmıştır (bkz.
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) — hangi projelerden
ilham alındığı ve lisans/AGPL riskinin nasıl yönetildiği).

## Öne Çıkan Özellikler

- **Türk plaka formatına özel doğrulama** — il kodu + harf + rakam
  kombinasyonlarını (örn. `34 ABC 12`) doğrulayan, OCR karakter
  karışıklıklarını (Türkçe karakter/rakam) toparlayan bir doğrulayıcı.
- **Çoklu kamera desteği** — her kamera bağımsız bir worker sürecinde
  RTSP akışını işler, API'ye görüntü gönderir.
- **Şifrelenmiş izleme listesi** — plaka ve notlar veritabanında Fernet
  ile şifreli tutulur, eşleştirme sızdırmayan bir hash ile yapılır (KVKK
  uyumu için).
- **Rol tabanlı yetkilendirme** — yönetici / operatör / izleyici rolleri,
  JWT tabanlı oturum.
- **Canlı web paneli** — WebSocket ile anlık tespit akışı, izleme listesi
  ve kamera yönetimi, tespit kayıt geçmişi.
- **Docker Compose ile tek komutla kurulum** — API + arka plan kamera
  worker'ı ayrı konteynerlerde, yatayda ölçeklenebilir.

## Mimari

```
[RTSP Kamera 1..N] --> [camera_worker.py]  --HTTP(JPEG)-->  [FastAPI API]
                                                                 |
                                                    [detector] --> [OCR] --> [plaka doğrulama]
                                                                 |
                                                    [SQLite/PostgreSQL]  <-- şifreli izleme listesi
                                                                 |
                                                    [WebSocket] --> [Web Paneli (static/)]
```

- `app/vision/detector.py` — iki değiştirilebilir tespit motoru:
  - `HaarCascadePlateDetector`: OpenCV ile gelen, ek model/lisans
    gerektirmeyen demo/düşük maliyetli motor.
  - `OnnxPlateDetector`: Eğitilmiş bir YOLO tabanlı modelin ONNX haline
    getirilip `onnxruntime` ile çalıştırıldığı üretim motoru (bkz. aşağıda
    **Model Tedariki**).
- `app/vision/ocr.py` — değiştirilebilir OCR motoru: varsayılan olarak
  **Tesseract** (tamamen çevrimdışı), opsiyonel olarak EasyOCR (bkz.
  **OCR Motoru Seçimi**).
- `app/camera_worker.py` — kamera başına RTSP'den kare alıp API'ye gönderen
  bağımsız süreç; API sürecinden izole, yatayda ölçeklenebilir.

Her katman (tespit motoru, OCR motoru, veritabanı modelleri, API route'ları,
panel arayüzü) birbirinden ayrı dosyalarda ve arayüz (interface) üzerinden
bağlı olacak şekilde tasarlandı; bu sayede ileride bir bileşeni değiştirmek
veya kaldırmak diğer katmanları bozmadan yapılabilir.

## Model Tedariki (Önemli)

Bu depo bir eğitilmiş plaka tespit modeli **içermez**. Varsayılan olarak
OpenCV'nin hazır kaskad dosyasıyla çalışan düşük maliyetli bir demo motoru
aktiftir. Üretim kalitesinde doğruluk için:

1. Türk plakaları üzerinde eğitilmiş bir YOLO tabanlı modeli ONNX formatına
   dönüştürüp `models/plate_detector.onnx` yoluna yerleştirin, **veya**
2. Bu işi bir yükleniciden veya Ultralytics Enterprise lisansı ile model
   sağlayan bir tedarikçiden satın alın.

`ultralytics` paketi (eğitim/aktarım aracı) **AGPL-3.0** lisanslıdır ve
yalnızca geliştirme ortamında kullanılmalı, ürünle birlikte dağıtılan
çalışma zamanına dahil edilmemelidir — detaylar için
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## OCR Motoru Seçimi

| Motor | `.env` ayarı | İnternet gerekir mi? | Not |
|---|---|---|---|
| **Tesseract** (varsayılan) | `OCR_ENGINE=tesseract` | Hayır | Docker imajına apt ile gömülür, tamamen çevrimdışı çalışır |
| EasyOCR (opsiyonel) | `OCR_ENGINE=easyocr` | İlk çalıştırmada evet* | Daha yüksek doğruluk, `pip install -r requirements-easyocr.txt` gerekir |

\* İnternetsiz kurulumda EasyOCR kullanmayın; ya Tesseract'ta kalın ya da
model ağırlıklarını Docker imajını **derlerken** (internet varken) önceden
indirip imaja gömün.

## Kurulum

```bash
make setup                     # .env dosyasini olusturur
# .env icinde JWT_SECRET_KEY ve WATCHLIST_ENCRYPTION_KEY icin onerilen komutu calistirip degerleri yapistirin

make up                        # imajlari derler ve baslatir (docker compose up -d --build)
make seed-admin PASSWORD=GucluBirSifre123
```

Panel: `http://localhost:8010` (giriş: `admin` / belirlediğiniz şifre).
Bu makinede 8010 portu da doluysa `.env` içindeki `API_PORT` değerini
değiştirin (örn. `API_PORT=8011`).

Diğer komutlar: `make down` (durdur), `make logs` (canlı log), `make test`
(birim testleri), `make package` (aşağıdaki internetsiz kurulum paketini
oluşturur).

## İnternetsiz (Air-Gapped) Kurulum

Ürün, imaj **bir kez internetli bir makinede derlendikten sonra** hiçbir
çalışma zamanı internet bağlantısı gerektirmez (varsayılan Tesseract OCR +
yerel ONNX/Haar tespit motoru + tüm frontend dosyaları yerel). İnternetsiz
bir saha/müşteri sunucusuna kurmak için:

```bash
make package                   # sertek-alpr-offline.tar dosyasini uretir
```

Bu `.tar` dosyasını, `docker-compose.yml`, `.env` ve (varsa)
`models/plate_detector.onnx` dosyasıyla birlikte hedef sunucuya taşıyın:

```bash
docker load -i sertek-alpr-offline.tar
docker compose up -d           # --build KULLANMAYIN, imaj zaten yuklu
```

Worker'ın API'ye bağlanabilmesi için `.env` dosyasına bir servis kullanıcısı
tanımlayın:

```
WORKER_USERNAME=kamera-worker
WORKER_PASSWORD=...
```

ve bu kullanıcıyı `seed_admin` script'ine benzer şekilde (veya panelden
"Kullanıcılar" ile) oluşturun.

## Geliştirme ve Testler

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

pytest
```

Her push/PR'da `.github/workflows/ci.yml` ile testler ve sözdizimi kontrolü
otomatik çalışır (GitHub Actions).

---

## Sertek Bilişim İçin Ticarileştirme Rehberi

### Hedef Müşteri Segmentleri

| Segment | İhtiyaç | Satış Modeli |
|---|---|---|
| Site / apartman yönetimleri | Sakin + ziyaretçi araç girişi kontrolü | Kurulum + yıllık bakım |
| Otoparklar (özel/AVM) | Ücretlendirme entegrasyonu, kapasite takibi | Kurulum + kamera başına lisans |
| Fabrika / OSB girişleri | Personel + tedarikçi araç takibi, güvenlik | Kurulum + SLA'lı bakım sözleşmesi |
| Belediye / toplu konut | Yasak bölge / kara liste takibi | İhale bazlı proje satışı |

### Önerilen Fiyatlandırma Modeli

- **Kurulum bedeli**: kamera sayısına ve mevcut CCTV altyapısına göre proje
  bazlı teklif (donanım hariç yazılım + entegrasyon işçiliği).
- **Yıllık lisans/bakım**: kamera başına yıllık ücret (güncelleme, destek,
  KVKK danışmanlığı dahil).
- **Opsiyonel bulut yedekleme/SaaS paneli**: aylık abonelik (ileride çoklu
  şube/merkezi izleme ihtiyacı olan müşteriler için).

### KVKK ve Uyumluluk

Plaka ve kamera görüntüsü 6698 sayılı KVKK kapsamında kişisel veri
sayılabilir. Her kurulumda:

- Giriş noktalarında aydınlatma metni/tabelası bulunmalı,
- Veri saklama süresi netleştirilmeli (öneri: tespit kayıtları için 30-90
  gün, izleme listesi süresiz ama düzenli gözden geçirme ile),
- Gerekiyorsa VERBİS kaydı müşteri tüzel kişiliği adına yapılmalı,
- Bu depodaki şifreleme (Fernet) ve hash tabanlı eşleştirme, "teknik ve
  idari tedbir" yükümlülüğüne katkı sağlar ancak hukuki uyum için KVKK
  danışmanlığı önerilir.

### Rekabet Konumlandırması

Rakip ürünler genelde ya (a) yurt dışı ANPR paketlerinin Türkçe'ye
uyarlanmamış hali ya da (b) tek kameralı, panel/izleme listesi olmayan
üniversite bitirme projesi kalitesinde açık kaynak kodlardır. Sertek
ALPR'nin farkı: Türk plaka formatına özel doğrulama, çoklu kamera +
rol tabanlı web paneli + KVKK'ya uygun şifreleme bir arada, yerinde
kurulum olarak anahtar teslim sunulabilir.

### Yol Haritası (Sonraki Adımlar)

1. Gerçek bir Türk plakası veri setiyle YOLO modeli eğitip ONNX'e aktarma
   (demo Haar cascade motorunun yerine).
2. Bariyer/kapı kontrol sistemleriyle (Wiegand/röle) donanım entegrasyonu.
3. Mobil uygulama (güvenlik görevlisi için anlık bildirim).
4. Çoklu şube/merkezi izleme için bulut SaaS sürümü.
5. Araç tipi, renk ve marka tanıma gibi ek analiz modülleri (üst segment
   fiyatlandırma için).
