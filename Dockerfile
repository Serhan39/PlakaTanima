FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 tesseract-ocr tesseract-ocr-tur \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# EasyOCR (opsiyonel, daha yuksek OCR dogrulugu icin - bkz. requirements-easyocr.txt)
# varsayilan olarak da kuruludur; hangisinin KULLANILACAGI .env icindeki
# OCR_ENGINE ile seçilir (varsayilan: tesseract, degisiklik gerekmez).
# torch'u ONCE CPU-only resmi indeksten kuruyoruz: pip'in varsayilan
# indeksi, sunucumuzda hic kullanilmayan (gpu=False) CUDA/NVIDIA
# paketlerini de indirir (~3.2GB fazladan) - CPU-only wheel bunu tamamen
# atlayip imaji ~1.4GB'a indiriyor.
COPY requirements.txt requirements-easyocr.txt ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install --no-cache-dir -r requirements.txt -r requirements-easyocr.txt

# EasyOCR model agirliklarini BUILD ANINDA (internet varken) indirip imaja
# gomer - boylece OCR_ENGINE=easyocr secildiginde konteyner CALISMA ANINDA
# internete ihtiyac duymaz (air-gapped kurulumlarda da calisir, build
# makinesinde internet oldugu surece).
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False)"

COPY app ./app
COPY static ./static
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
