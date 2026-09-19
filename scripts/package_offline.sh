#!/usr/bin/env bash
# Internetli bir makinede Docker imajlarini derleyip tek bir tar dosyasina
# paketler; bu dosya internetsiz (air-gapped) bir sunucuya tasinip
# `docker load` ile yuklenebilir. Kullanim:
#   ./scripts/package_offline.sh [cikti-dosyasi.tar]
set -euo pipefail

OUTPUT="${1:-sertek-alpr-offline.tar}"
IMAGE_TAG="sertek-alpr:latest"

echo "==> Imaj derleniyor ($IMAGE_TAG)..."
docker build -t "$IMAGE_TAG" .

echo "==> Imaj $OUTPUT dosyasina kaydediliyor..."
docker save -o "$OUTPUT" "$IMAGE_TAG"

echo "==> Tamamlandi: $OUTPUT"
echo ""
echo "Internetsiz sunucuda kurulum:"
echo "  1) Bu tar dosyasini ve depo klasorunun tamamini (docker-compose.yml, .env, models/) tasiyin"
echo "  2) docker load -i $OUTPUT"
echo "  3) docker compose up -d"
echo ""
echo "Not: models/ klasorundeki .onnx dosyasini ve .env icindeki anahtarlari da tasimayi unutmayin."
