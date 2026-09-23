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
- **Canlı web paneli** — WebSocket ile anlık tespit akışı, son geçen aracın
  fotoğrafı, son 10 geçişin küçük fotoğraflı listesi, izleme listesi ve
  kamera yönetimi, tespit kayıt geçmişi.
- **Raporlama** — tarih/kamera/kategori/plaka bazlı filtrelenebilir olay
  raporu, özet istatistik kartları, CSV dışa aktarma.
- **E-posta bildirimleri** — aranan/kara liste plakası görülünce anlık
  uyarı e-postası, her gün otomatik gönderilen günlük özet rapor
  (SMTP yapılandırılmazsa özellik sessizce devre dışı kalır).
- **I/O kart (röle) entegrasyonu** — kamera başına yapılandırılabilir,
  plaka izinli/personel listesiyle eşleşince bariyere/dış üniteye HTTP,
  ham TCP veya Modbus TCP üzerinden açık sinyali gönderir. Panelden
  "Röleyi Test Et" ile donanım gerçek bir kamera olmadan da denenebilir.
- **Otopark doluluk takibi** — kameraları "Giriş"/"Çıkış" olarak
  işaretleyerek o an içeride kaç araç olduğunu ve doluluk oranını canlı
  panelde gösterir.
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
- `app/camera_worker.py` — kamera başına RTSP'ye BİR KERE bağlanıp sürekli
  kare okuyan bağımsız süreç (API sürecinden izole, yatayda ölçeklenebilir).
  Okuma ve gönderme ayrı thread'lerdedir (yavaş bir HTTP/OCR isteği kare
  okumayı asla bloke etmez). Okunan kareler hem canlı önizleme önbelleğine
  (sık, `PREVIEW_INTERVAL_SECONDS`) hem de tespite (seyrek,
  `CAPTURE_INTERVAL_SECONDS`) gönderilir.
- Panelin "Canlı Kameralar" ızgarası, `GET /api/cameras/{id}/stream`
  üzerinden gerçek bir MJPEG (`multipart/x-mixed-replace`) video akışı
  izler — tarayıcı bunu `<img>` etiketiyle native oynatır, JS tarafında
  polling yoktur. Kimlik doğrulama, önce normal JWT ile alınan kısa
  ömürlü, tek kameraya özel bir "stream token" (`app/stream_tokens.py`,
  `POST /api/cameras/{id}/stream-token`) ile yapılır — `<img src="...">`
  özel bir Authorization header taşıyamadığı için.

Her katman (tespit motoru, OCR motoru, veritabanı modelleri, API route'ları,
panel arayüzü) birbirinden ayrı dosyalarda ve arayüz (interface) üzerinden
bağlı olacak şekilde tasarlandı; bu sayede ileride bir bileşeni değiştirmek
veya kaldırmak diğer katmanları bozmadan yapılabilir.

## Model Tedariki (Önemli)

Bu depo bir eğitilmiş plaka tespit modeli **içermez** (`models/*.onnx`
`.gitignore`'dadır — git'e commit edilmez, her kurulumda ayrıca
yerleştirilir). Dosya yoksa `build_default_detector()` OpenCV'nin hazır
kaskad dosyasıyla çalışan düşük maliyetli bir demo motoruna geriye düşer;
bu motor **gerçek kamera görüntüsünde genelde yetersiz kalır** (açı,
mesafe, ışık değişimlerine dayanıksız) — hangi motorun aktif olduğu
sunucu loglarında `[detect] ONNX motoru kullaniliyor: ...` ya da
`[detect] ONNX model dosyasi bulunamadi ... Haar Cascade demo motoruna
geciliyor` satırıyla açıkça görülür.

Üretim kalitesinde doğruluk için üç yol:

1. **Önerilen, ücretsiz başlangıç noktası:** Türk plakaları üzerinde
   eğitilmiş, Apache-2.0 lisanslı, hazır bir YOLOv8 ONNX modeli mevcut —
   [Semihocakli/turkish-plate-recognition-w-yolov8-onnx-to-engine-cpp](https://github.com/Semihocakli/turkish-plate-recognition-w-yolov8-onnx-to-engine-cpp)
   deposundaki `detection_weights/best.onnx` dosyasını indirip
   `models/plate_detector.onnx` olarak yerleştirin. Girdi/çıktı tensör
   formatı (`[1,3,640,640]` → `[1,5,8400]`, tek sınıf) bu projedeki
   `OnnxPlateDetector` ile doğrudan uyumludur, kod değişikliği
   gerektirmez — kod içi sentetik bir test görüntüsüyle doğrulanmıştır
   (bkz. [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)). Bu, genel
   amaçlı bir açık kaynak modelidir; gerçek saha koşullarınızda (kendi
   kamera açınız, mesafeniz, ışığınız) doğruluğunu mutlaka test edin —
   yetersiz kalırsa aşağıdaki 2. veya 3. yola geçin.
2. Kendi kamera görüntülerinizle (yukarıdaki modeli başlangıç noktası
   olarak kullanıp) ek eğitim/fine-tuning yapıp `models/plate_detector.onnx`
   yoluna yerleştirin, **veya**
3. Bu işi bir yükleniciden veya Ultralytics Enterprise lisansı ile model
   sağlayan bir tedarikçiden satın alın.

`ultralytics` paketi (eğitim/aktarım aracı) **AGPL-3.0** lisanslıdır ve
yalnızca geliştirme ortamında kullanılmalı, ürünle birlikte dağıtılan
çalışma zamanına dahil edilmemelidir — detaylar için
[THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).

## OCR Motoru Seçimi

| Motor | `.env` ayarı | Çalışırken internet gerekir mi? | Not |
|---|---|---|---|
| **Tesseract** (varsayılan) | `OCR_ENGINE=tesseract` | Hayır | Docker imajına apt ile gömülür, tamamen çevrimdışı çalışır |
| EasyOCR (opsiyonel) | `OCR_ENGINE=easyocr` | Hayır | Küçük/gerçek dünya plaka kırpmalarında genelde daha yüksek doğruluk ve daha anlamlı güven puanı verir |

İkisi de Dockerfile'da varsayılan olarak kuruludur (`requirements-easyocr.txt`
dahil, CPU-only torch ile ~1.4GB imaj boyutu eklenir) ve EasyOCR'ın model
ağırlıkları **build anında** (internet varken) indirilip imaja gömülür — yani
`OCR_ENGINE=easyocr` seçseniz bile konteyner çalışırken internete ihtiyaç
yoktur. Değiştirmek için `.env`'de `OCR_ENGINE` değerini güncelleyip
`docker compose up -d` yapmanız yeterli (yeniden derlemeye gerek yok, motor
seçimi çalışma zamanında okunur).

## Röle / I-O Kart Entegrasyonu

Kameralar sekmesinde her kamera icin bagimsiz bir role yapilandirilabilir:

| Tip | Hedef alani | Komut alani | Aciklama |
|---|---|---|---|
| HTTP | Tam URL (`http://192.168.1.50/open`) | - | Cogu ag tabanli bariyer kartinda hazir bir HTTP tetikleme adresi olur |
| TCP | `ip:port` | Ham metin komutu (orn. `REL1ON\r\n`) | Kart ureticisinin dokumantasyonundaki komutu birebir yazin |
| Modbus TCP | `ip:port` (port bos ise 502) | Coil (bobin) adresi, orn. `0` | Fonksiyon kodu 0x05 (Write Single Coil) kullanilir |

"Tetikleyen kategoriler" alanina (varsayilan `allowed,staff`) hangi izleme
listesi kategorisinde role acilacagini yazin. Donaniminiz henuz kurulu
degilse veya kamera yoksa, "Röleyi Test Et" butonuyla API'nin donanima
ulasip ulasamadigini kamerasiz da deneyebilirsiniz.

## Raporlama ve E-posta Bildirimleri

**Raporlar** sekmesinden tarih araligi, kamera, kategori ve plakaya gore
filtrelenebilir bir olay listesi, ozet sayilar ve CSV disa aktarma
kullanilabilir. E-posta bildirimleri icin `.env` icindeki `SMTP_*`
degiskenlerini doldurun:

- `ALERT_CATEGORIES` + `ALERT_TO`: bu kategoride bir plaka gorulunce aninda
  uyari e-postasi gonderilir (varsayilan: aranan ve kara liste).
- `DAILY_REPORT_TO` + `DAILY_REPORT_HOUR`: her gun belirtilen saatte otomatik
  gunluk ozet raporu gonderilir. `DAILY_REPORT_TO` bos birakilirsa gunluk
  rapor gonderilmez. Panelden "Gunluk Raporu Simdi Gonder" ile test edilebilir.

`SMTP_HOST` bos birakilirsa e-posta ozelligi sessizce devre disi kalir,
sistemin geri kalani etkilenmez.

## Tespit Bolgesi (ROI) - Genis Acili Kameralar Icin

Geniş açılı bir kamera bir avlu/girişin tamamını gösteriyorsa, uzaktaki bir
aracın plakası tespit motorunun çalıştığı 640x640 piksele küçültülünce
kaybolabilir — model bir "plaka" bile göremez. **Kameralar** sekmesinde her
kameranın yanındaki **"Bölgeyi Düzenle"** ile, araçların gerçekte geçtiği/
plakanın görüneceği alanı (kameradan alınan örnek görüntü üzerinde 2
tıklama: sol-üst ve sağ-alt köşe) işaretleyin. Tespit artık **önce bu
bölgeye kırpılmış (dijital yakınlaştırılmış) kareyle** çalışır — kamera
donanımı veya konumu değişmeden efektif çözünürlük artar. Bölge
tanımlanmazsa (veya "Bölgeyi Kaldır" ile temizlenirse) eskisi gibi tüm kare
kullanılır. Değişiklik bir sonraki tespitten itibaren geçerlidir, worker
yeniden başlatmaya gerek yoktur.

## Otopark Doluluk Takibi

Kameralar sekmesinde bir kamerayi "Giris", bir digerini "Cikis" olarak
isaretleyin. Giris kamerasinda tespit edilen her plaka "icerde" sayilir,
cikis kamerasinda tespit edilince listeden dusurulur. Canli Tespitler
sekmesindeki widget o an icerideki arac sayisini ve doluluk yuzdesini
gosterir; kapasite `PARKING_CAPACITY` ile (veya panelden "Kapasiteyi
Duzenle" ile, kalici olarak veritabaninda) ayarlanir.

## Is Makinasi Takip (opsiyonel, varsayilan gizli)

Birden fazla alana (fabrika ici bolge) sahip tesisler icin: her alanin
giris/cikis kapisina bir kamera takilir, is makinesinin uzerine firmanin
kendi bastiracagi ozel bir kod/etiket konur. Bu ozellik standart Turkiye
plaka formatini **zorunlu kilmaz** — OCR, herhangi bir alfanumerik kodu
(en az `EQUIPMENT_MIN_CODE_LENGTH` karakter) kabul eder.

- **Varsayilan olarak gizlidir.** Sekme, sadece yetkili bir kullanici panelin
  sag ust kosesindeki "Is Makinasi Takip" onay kutusunu isaretleyip ozelligi
  acana kadar hicbir kullaniciya gorunmez.
- **Rolden bagimsiz yetki**: bu onay kutusunu sadece yoneticiler degil,
  "Kullanicilar" sekmesinden (sadece yoneticiler erisebilir) bir izleyici
  hesabina ozel olarak verilen "Is Makinasi Takibini Acip Kapatabilir"
  yetkisiyle isaretlenmis izleyiciler de gorup kullanabilir. Bu, o
  kullaniciya baska hicbir yonetici hakki (kamera/kullanici yonetimi vb.)
  vermez, sadece bu tek anahtari acar.
- **Alan (Zone)**: adlandirilmis bolgeler (orn. "A Alani", "B Alani").
- **Kapi (Gate)**: bir alana bagli kamera konumu.
- **Cizgi (sanal tripwire) tespiti**: kamera genis bir alani goruyorsa
  (sadece dar kapi bosluguna degil), aracin goruntude "bulunmasi" ile
  kapidan "gecmesi" ayni sey degildir. Panelde her kapi icin, kameradan
  alinan ornek goruntu uzerinde tiklayarak bir gecis cizgisi cizilir
  (Kapilar tablosunda "Cizgiyi Duzenle"). `app/equipment_gate_worker.py`,
  RTSP akisini SUREKLI okuyup plakayi/kodu kareler arasinda basit bir
  merkez-nokta takibiyle izler ve cizgiyi FIILEN gectigi an bunu bildirir
  — sadece kameranin bir seyi "gormesi" degil, gercek bir gecis olmasi
  aranir.
- **Giren/cikan ayrimi**: ayni fiziksel kapidan hem giren hem cikan arac
  olabilecegi icin yon kapiya sabit degildir. Cizgiyi cizerken ayrica
  cizginin hangi tarafinin "icerisi" (ilgili alan) oldugu isaretlenir;
  bir aracin gectikten sonraki tarafi bu referansla ayni ise **GIRIS**,
  degilse **CIKIS** olarak otomatik ayirt edilir (bkz. `app/vision/tracker.py`).
- **Yanlis alarm onleme**: ayni kod/kapi icin `EQUIPMENT_CROSSING_DEBOUNCE_SECONDS`
  (varsayilan 30sn) icinde tekrar eden okumalar tek bir gecis sayilir.
- Canli Izleme paneli "ABCD plakali arac B alaninda" / "... disarida" gibi
  mesajlari aninda WebSocket ile gosterir; Guncel Durum tablosu tum
  makinelerin son bilinen konumunu listeler.
- **Gecis Kayitlari**: tarih/alan/kapi/plakaya gore filtrelenebilir, hangi
  aracin hangi alandaki hangi kapidan gectigini gosteren tablo.
- **Zaman Raporu**: secilen tarih araliginda her aracin hangi alanda (veya
  disarida) toplam ne kadar sure gecirdigini hesaplar.
- Kapi kameralarindan goruntu almak icin `app/equipment_gate_worker.py`
  kullanilir (docker-compose icinde `equipment-worker` servisi olarak
  hazir gelir, `.env` icinde `EQUIPMENT_WORKER_USERNAME`/`_PASSWORD`
  doldurulmadan calismaz, hata vermeden bekler). Bir kapinin cizgisi
  panelden degistirildiginde, worker'in bunu almasi icin yeniden
  baslatilmasi gerekir: `docker compose restart equipment-worker`.

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

## Güncelleme Sonrası Veri Kaybı Olmaz (Otomatik Şema Güncellemesi)

`git pull` + `docker compose up -d --build` ile yeni bir sürüme geçtiğinizde,
uygulama açılışta veritabanı şemasını otomatik kontrol eder ve yeni
sürümde eklenmiş ama sizin veritabanınızda henüz bulunmayan sütunları
kendiliğinden ekler (`app/migrations.py`). Böylece mevcut kullanıcılar,
izleme listesi, kamera/geçit tanımları, tespit kayıtları vb. veriler
korunur; veritabanını silip sıfırdan kurmanıza gerek kalmaz. Bu mekanizma
her başlangıçta çalışır ve şema zaten güncelse hiçbir şey yapmaz
(idempotent).

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
2. Wiegand/kart okuyucu gibi ek erişim kontrol donanımlarıyla entegrasyon
   (HTTP/TCP/Modbus röle entegrasyonu zaten mevcut, bkz. yukarıda).
3. Mobil uygulama (güvenlik görevlisi için anlık bildirim).
4. Çoklu şube/merkezi izleme için bulut SaaS sürümü.
5. Araç tipi, renk ve marka tanıma gibi ek analiz modülleri (üst segment
   fiyatlandırma için).
