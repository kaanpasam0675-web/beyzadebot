Nova Bot - Railway / Render'a Yükleme Rehberi
=============================================

Bu rehber botu Railway'a (ya da Render) yüklerek bilgisayar kapalıyken bile
çalışır durumda tutmanı sağlar. (Ses kanalı özelliği bulut ortamlarında
genelde desteklenmez - bot yine çalışır ve tüm diğer özellikler kullanılır.)

HAZIRLIK
--------
1) Bu klasorde hazir dosyalar:
   - railway.json        -> Railway yol tarifi
   - render.yaml         -> Render yol tarifi
   - Procfile            -> Calistirma komutu
   - requirements-linux.txt -> Bulut bagimliliklari (davey yok, Linux icin)

2) Deponuz (GitHub reposu) gerekir. GitHub'a bu klasoru yukleyin.
   - Proje zaten repo degilse: https://github.com/new ile boş repo olustur
   - Komutla yukleme ornegi:
       git init
       git add .
       git commit -m "Nova Bot"
       git remote add origin https://github.com/KULLANICI_ADIN/novabot.git
       git push -u origin main

RAILWAY (https://railway.app)
-----------------------------
1) railway.app -> Sign Up (GitHub ile giris)
2) New Project -> Deploy from GitHub repo -> bu reposu sec
3) Settings -> Variables -> ekle:
     DISCORD_TOKEN       = (Discord bot token'in)
     DASHBOARD_PASSWORD  = (istedigin bir parola)
4) Deploy et. Bot otomatik baslar.
   - railway.json hazir oldugu icin build/start komutlari otomatik gelir.

RENDER (https://render.com)
---------------------------
1) render.com -> Sign Up (GitHub ile)
2) New -> Blueprint (Blueprints'teki render.yaml'i automatic algilar)
   VEYA New -> Web Service -> repoyu bagla:
     - Environment: Python
     - Build Command: pip install -r requirements-linux.txt
     - Start Command: python dashboard/app.py
3) Environment -> add env var:
     DISCORD_TOKEN       = (token)
     DASHBOARD_PASSWORD  = (parola)
4) Deploy. URL geldiğinde bot hazir.

DOGRULAMA
---------
- Deploy loglarinda "[OK] Bot giris yapti: Nova Bot" satirini gormelisin.
- Discord'da !help sunucunda 1 mesaj doner.

NOTLAR
------
- Bu kurulum PC bagimsiz 7/24 calisir (Render/Railway uykuya sokmamasi
  icin plan secimi gerekebilir; ucretsiz kotalar farklidir).
- .env dosyasi bulutta KULLANILMAZ; her sey env var olarak verildi.
  config.py zaten os.getenv ile okuyor.
- Yerelde bot.db verileri (/opt yerine) burada baska sunucuda sifir
  baslar; turuncu verileri tasimak istersen bot.db dosyasini da repoya
  ekleyebilirsin.