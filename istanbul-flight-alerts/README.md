# Istanbul Flight Alerts — Vizesiz Uçuş Fırsat Radarı

İstanbul (**IST, SAW**) kalkışlı 19 vizesiz hedef havalimanındaki direkt, gidiş–dönüş biletlerin önbellek fiyatlarını kontrol edip kritik fiyat düşüşlerinde e-posta göndermek üzere hazırlanmıştır. T.C. **bordo pasaport** esas alınmıştır.

## GitHub yayını ve durum

Kod bu profil deposunda **ayrı bir alt proje** olarak yayınlanmıştır; diğer GitHub projelerinin dosyaları değiştirilmemiştir. GitHub Actions iş akışı kökteki `.github/workflows/istanbul-flight-alerts.yml` dosyasında bulunur.

- **Kod ve otomatik birim testleri**: Aktif. Push tetiklemesi ve dört zamanlanmış tetikleyici vardır.
- **Gerçek bilet taraması / e-posta**: Yalnızca Travelpayouts ve SMTP Secrets tanımlandıktan sonra aktiftir. Eksikse workflow testleri yapar ve taramayı bilinçli olarak atlar.
- **HTTP API**: Kod hazır; GitHub Actions bir web sunucusu barındırmadığı için çevrimiçi API erişimi ayrıca barındırma gerektirir.

## Gerçek taramayı açmak için

[GitHub Secrets](https://github.com/oguzpoyrazyasin/oguzpoyrazyasin/settings/secrets/actions) alanına bu değerleri ekleyin. **Şifre ve token'ları asla kod dosyasına veya sohbete yazmayın.**

| Secret | Açıklama |
| --- | --- |
| `TRAVELPAYOUTS_TOKEN` | [Travelpayouts](https://www.travelpayouts.com/) Flight Data API erişim anahtarı |
| `SMTP_HOST` | Örneğin `smtp.gmail.com` |
| `SMTP_PORT` | Gmail için `465` (eklenmezse 465) |
| `SMTP_USER` | E-posta gönderen adres |
| `SMTP_PASSWORD` | SMTP uygulama şifresi; Gmail için **App Password**, normal hesap şifresi değil |
| `ALERT_TO` | Fırsat bildirimlerini alacak e-posta adresi |

Anahtarlar girildikten sonra [Actions sayfasında](https://github.com/oguzpoyrazyasin/oguzpoyrazyasin/actions/workflows/istanbul-flight-alerts.yml) “Run workflow” ile elle çalıştırılabilir; takip eden taramalar zamanlamayla devam eder.

## Algoritma

- 21–180 gün sonrasındaki gidiş tarihi; 2–10 gece konaklama; direkt uçuş; TRY.
- Kişi başı gidiş–dönüş fiyatı **5.000 TRY veya altında** ise fırsat uyarısı.
- Aynı kalkış/varış ve gidiş–dönüş tarihindeki en az üç farklı günün fiyat medyanından **%30 ve 1.800 TRY** düşüşte uyarı.
- Aynı bilet için tekrar bildirim, son bildirilen fiyattan daha ucuzsa ve ek %10 düşüş veya 7 günlük bekleme koşulu gerçekleşmişse.
- Fiyat geçmişi `data/state.json` içinde tutulur, asla giriş bilgisi içermez.
- GitHub Actions yaklaşık **04:17 / 10:17 / 16:17 / 22:17 Türkiye saatiyle** tarama başlatır. Planlanan işler gecikebilir.

## API ve geliştirme

Python 3.12+ ile bu klasörde:

```bash
python -m unittest discover -s tests -v
python flight_alerts.py demo
python flight_alerts.py scan
pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

REST uçları: `GET /health`, `GET /destinations`, `GET /deals` ve `POST /scan`. Sonuncusu için `ADMIN_API_KEY` sunucu ortam değişkeni ve `X-API-Key` istek başlığı gereklidir. API üretimde HTTPS, erişim kontrolü ve kalıcı veritabanı ile dışarı açılmalıdır.

**Sınırlamalar:** Travelpayouts verisi önbellektir ve tüm destinasyonlarda sonuç bulunmasını garanti etmez. Tarihsel medyan karşılaştırması bagaj/havayolu/sınıf farklarını normalize etmez. Liste elle hazırlanmıştır; seyahatten önce [Dışişleri Bakanlığı giriş/vize koşullarını](https://www.mfa.gov.tr/turk-vatandaslarinin-tabi-oldugu-vize-uygulamalari.tr.mfa) kontrol edin. Kesin bilet fiyatı yalnızca satın alma ekranında doğrulanabilir.
