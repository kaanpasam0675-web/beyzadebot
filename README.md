# 🤖 Her Şey Dahil Discord Botu

Python + discord.py ile yazılmış, web dashboard'dan (tarayıcı) yönetilebilen kapsamlı bir Discord botu.

## ✨ Özellikler

| Kategori | Özellikler |
|---|---|
| 🛡️ Moderasyon | Kick, ban, unban, mesaj temizleme, uyarı sistemi (uyar/uyarılar/uyarı-sil), geçici susturma, prefix değiştirme, otomatik rol, karşılama mesajı |
| 🎮 Eğlence | Zar at, yazı-tura, sihirli 8 top, kaç-cm, pp, sunucu bilgi, embed gönder |
| 📈 Seviye / XP | Mesaj başına XP, seviye atlama bildirimi, `!seviye`, liderlik tablosu `!top` |
| 🎫 Ticket | `!ticket` ile destek bileti kanalı, `!kapat` ile kapatma |
| 🎛️ Özel Komutlar | **Dashboard'dan** komut ekle; metin/embed yanıtı + rol ver/rol al/sustur/at/ban aksiyonu |
| 🌐 Dashboard | Tarayıcıdan sunucu seçme, özel komut ekleme/silme, prefix değiştirme |

## 📋 Kurulum

1. **Python 3.12** kurulu olmalı (https://www.python.org/downloads/)
2. `kurulum.bat` çift tıklayıp bekleyin (bağımlılıkları kurar)
3. `.env.example` dosyasını kopyalayıp `.env` olarak yeniden adlandırın
4. `.env` dosyasını düzenleyin:
   - `DISCORD_TOKEN` → kendi bot token'ınız (https://discord.com/developers/applications → Bot → Reset Token)
   - `DASHBOARD_PASSWORD` → dashboard giriş şifreniz
   - `DASHBOARD_PORT` → port (varsayılan 5000)

### Discord Botunu Oluşturma
1. https://discord.com/developers/applications adresinde **New Application** oluşturun.
2. **Bot** sekmesine gidin, token'ı kopyalayın (`.env` içine yapıştırın).
3. **Privileged Gateway Intents** altında **MESSAGE CONTENT INTENT** ve **SERVER MEMBERS INTENT**'i açın.
4. **OAuth2 → URL Generator**: scopes'a `bot` ve `applications.commands` ekleyin. İstediğiniz yetkileri (Administrator) seçin, çıkan URL'yi tarayıcıda açıp sunucunuza davet edin.
5. Botu davet ettikten sonra Discord'da `!help` yazın; tüm komutları görürsünüz.

## 🚀 Çalıştırma

`baslat.bat` dosyasına çift tıklayın (hem Discord botu hem dashboard başlar).

- **Dashboard:** http://127.0.0.1:5000 (şifre: `.env`'deki `DASHBOARD_PASSWORD`)

## 🎛️ Dashboard Kullanımı

1. Tarayıcıda http://127.0.0.1:5000 açın, şifrenizle girin.
2. Üstten sunucunuzu seçin.
3. **Yeni Özel Komut** formunda:
   - **Komut Adı**: örn. `selam` → Discord'da `!selam` yazınca tetiklenir
   - **Yanıt Metni**: botun yazacağı mesaj. Yer tutucular: `{user}`, `{mention}`, `{id}`, `{args}`, `{server}`
   - **Embed Başlığı/Açıklaması**: birlikte güzel bir embed kartı gönderir
   - **İşlem**: rol ver/rol al/sustur/at/ban gibi aksiyonlar
     - **Hedef Kullanıcı**: aksiyonun uygulanacağı kullanıcı (ad veya ID)
     - **Değer**: rol adı/ID, susturma dakikası, gönderilecek mesaj
4. Kaydet → Discord'da test edin.

## 🗂️ Proje Yapısı

```
cogs/
  moderation.py   # moderasyon komutları
  fun.py          # eğlence komutları
  levels.py       # seviye / XP
  tickets.py      # ticket sistemi
  custom.py       # özel komut çalıştırıcı
dashboard/
  app.py          # Flask dashboard
  templates/      # HTML sayfalar
  static/         # CSS
bot.py            # bot ana dosyası
database.py       # SQLite katmanı
config.py         # ayar okuma
baslat.bat        # (bot + dashboard) başlatma
kurulum.bat       # bağımlılık kurulumu
```

## ⚠️ Notlar

- Herhangi bir hata ile karşılaşırsan konsol çıktısını kontrol edin.
- Mute rolü otomatik oluşturulur; botun kanal izinlerini ayarlayabilmesi için `Manage Channels` yetkisi verin.
- Ticket kanalları kullanıcıya özel overrite'larla açılır.