#!/usr/bin/env bash
# Nova Bot - bulut (Oracle Cloud Free Tier / Ubuntu 22.04+) kurulum betiği
# Kullanım:  sudo bash deploy_install.sh
set -e

echo "[1/5] Sistem paketleri güncelleniyor..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl ffmpeg

echo "[2/5] Proje klonlanıyor/kopyalanıyor..."
APP_DIR="/opt/novabot"
mkdir -p "$APP_DIR"

# Eğer bu betik proje klasörü içinde çalıştırılıyorsa mevcut dosyaları kopyala
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/bot.py" ]; then
    cp -r "$SCRIPT_DIR"/. "$APP_DIR"/
else
    echo "!! bot.py bulunamadı. Proje dosyalarını bu klasöre koy."
    echo "!! (/opt/novabot veya bu betiğin bulunduğu klasör)"
    exit 1
fi

echo "[3/5] Python venv + bağımlılıklar kuruluyor..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-linux.txt

echo "[4/5] systemd servisi oluşturuluyor..."
cat > /etc/systemd/system/novabot.service <<'EOF'
[Unit]
Description=Nova Bot (Discord + Dashboard)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/novabot
EnvironmentFile=/opt/novabot/.env
ExecStart=/opt/novabot/venv/bin/python /opt/novabot/dashboard/app.py
Restart=always
RestartSec=5
# Çökmeye karşı sınırsız yeniden başlatma (7/24 açık kalır)
StartLimitIntervalSec=0
StartLimitBurst=0
User=root

[Install]
WantedBy=multi-user.target
EOF

echo "[5/5] Servis etkinleştiriliyor ve başlatılıyor..."
systemctl daemon-reload
systemctl enable novabot.service
systemctl restart novabot.service

echo ""
echo "====================  KURULUM TAMAM  ===================="
echo "  ÖNEMLİ: /opt/novabot/.env dosyasındaki DISCORD_TOKEN'u"
echo "  Discord geliştirici panelindeki token'ınla doldur!"
echo "  Sonra şunu çalıştır:  sudo systemctl restart novabot"
echo ""
echo "  Durum kontrolü:   sudo systemctl status novabot"
echo "  Logları izle:     sudo journalctl -u novabot -f"
echo "  Dashboard:        http://<sunucu-ip>:5000"
echo "==========================================================="
