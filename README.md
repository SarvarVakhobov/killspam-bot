<div align="center">

# 🛡️ Spam Protection Bot

**Guruhlarni 18+ fake akkauntlar va fishing havolalardan tozalaydigan, o‘z-o‘ziga xizmat ko‘rsatuvchi Telegram boti — behayo profil rasmlari va bio’lar, kattalar uchun spam-bot tuzoqlari hamda asl manzilini yashiradigan havolalar avtomatik o‘chiriladi.**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Built for @ertagakech](https://img.shields.io/badge/built%20for-%40ertagakech-26A5E4?logo=telegram&logoColor=white)](https://t.me/ertagakech)

🇺🇿 **O‘zbekcha** · 🇬🇧 [English](README.en.md) · 🇷🇺 [Русский](README.ru.md)

</div>

> ### 🤖 [@ertagakech](https://t.me/ertagakech) Telegram kanali uchun yaratilgan
> Ushbu bot **[@ertagakech](https://t.me/ertagakech)** uchun yaratilgan — sun’iy intellekt, avtomatlashtirish va shunga o‘xshash loyihalarni yaratish haqida ko‘proq bilish uchun kanalga qo‘shiling. 👉 **https://t.me/ertagakech**

## 🚀 Tayyor bot: [@spamliman_bot](https://t.me/spamliman_bot)

O‘zingiz server ko‘tarmoqchi bo‘lmasangiz, shu fork kodi asosida ishlab turgan **[@spamliman_bot](https://t.me/spamliman_bot)** («Spam Fake Accounts») botidan foydalaning:

1. @spamliman_bot’ni guruhingizga qo‘shing va **Xabarlarni o‘chirish** + **Foydalanuvchilarni bloklash** huquqlari bilan **admin** qiling.
2. Guruhda `/enable` deb yozing.
3. Bot bilan shaxsiy chatni ochib **Start** tugmasini bosing — shunda bot ogohlantirishlarni sizga yubora oladi.

Bot 18+ fake akkauntlar va fishing havolalarni o‘chiradi; oddiy suhbat, reklama va kanal havolalariga tegmaydi. Bu botda AI moderatsiyani uning operatori yoqadi.

---

## Bu nima

Hamjamiyat guruhlari — IT o‘quv guruhlari, kino muhokamasi va boshqalar — uchun Telegram moderatsiya boti. Har kim uni guruhiga qo‘shib, `/enable` buyrug‘ini berishi va darhol himoyaga ega bo‘lishi mumkin. Bot **ko‘p foydalanuvchili (multi-tenant)**: har bir guruh o‘zining Google Gemini kalitini ulashi mumkin (**BYOK**), operator esa kaliti yo‘q guruhlar uchun bitta **umumiy kalit** berishi mumkin. Hech qanday kalit bo‘lmasa ham bepul tekshiruvlar — profil rasmlarini mahalliy skanerlash, 18+ havolali bio’lar va yashirin fishing havolalar — guruhni himoya qilishda davom etadi.

## 🎯 Nimalar bloklanadi — va nimalar yo‘q

Bot **faqat ikki narsaga** qarshi choralar ko‘radi:

| Bloklanadi | Qanday aniqlanadi | Chora |
|---|---|---|
| **18+ fake akkauntlar** | aniq behayo profil rasmi (NudeNet, mahalliy) · 18+ so‘zlar yonida havola bo‘lgan bio | ban + o‘chirish |
| | AI xabar yoki bio’ni shahvoniy kontent yoki spam-bot tuzog‘i deb topadi | o‘chirish + 24 soat ovozsiz |
| **Fishing havolalar** | havola matnida bir sayt ko‘rinadi, lekin boshqasi ochiladi (`https://gov.uz/…` → `evil.cc`) | o‘chirish + 24 soat ovozsiz |
| | havola domenini VirusTotal antiviruslari zararli deb biladi | o‘chirish + 24 soat ovozsiz |

**Bloklanmaydi:** reklama va e’lonlar, a’zoning bio’sidagi o‘z kanali yoki taklif havolasi (`t.me/+…`), kripto haqidagi gaplar, haqoratlar, mavzudan tashqari suhbatlar, kino muhokamasi (yosh chegarasini tilga olish ham). Oldingi versiyalar bularning ayrimlari uchun odamlarni ovozsizlantirardi — bu qoidalar olib tashlandi.

**24 soat ovozsiz rejimda** a’zo guruhda qoladi — xabarlarni o‘qiy oladi, lekin yoza olmaydi — va cheklov o‘zi olinadi. Guruh adminlari (`OPERATOR_ALERTS=1` bo‘lsa operator ham) **Ban / Unmute** tugmalari bilan ogohlantirish oladi, shuning uchun xatoni bir bosishda tuzatish mumkin.

## ✨ Xususiyatlari

- **Ko‘p foydalanuvchili, o‘z-o‘ziga xizmat ko‘rsatuvchi** — botni qo‘shing, guruhda `/enable` bering, tamom. Har bir guruhning o‘z adminlari ogohlantirishlarni qabul qiladi.
- **18+ fake akkauntlarni aniqlash** — profil rasmlari NudeNet yordamida mahalliy tekshiriladi (bulutga so‘rov yuborilmaydi), noaniq rasmlar bo‘yicha chora ko‘rilmaydi. Bio va xabarlarni AI qatlami baholaydi — u faqat shahvoniy kontent va spam-bot tuzoqlarini belgilashga sozlangan.
- **Fishing havolalarni bloklash** — yashirin havolalar bepul va internetga murojaat qilmasdan aniqlanadi. VirusTotal API kaliti bo‘lsa, har bir havolaning asl domeni (va yuqori darajadagi domeni) ham tekshiriladi. Faqat domen yuboriladi, natijalar keshlanadi, yirik platformalar umuman tekshirilmaydi.
- **AI kalitlari: guruhniki yoki umumiy** — `/setkey` guruhning o‘z Gemini kalitini bir martalik veb-shakl orqali shifrlab saqlaydi. Operator o‘z kaliti yo‘q barcha guruhlar uchun bitta umumiy kalit o‘rnatishi mumkin (`/globalkey`); guruhning o‘z kaliti doim ustun turadi.
- **Operator uchun AI tugmasi** — `/ai` har bir guruhni AI holati bilan ko‘rsatadi va AI’ni barcha guruhlarda birdaniga yoki bittalab yoqib-o‘chiradi. Keyin qo‘shilgan guruhlar standart sozlamaga ergashadi.
- **Operatorga ban lentasi** — `OPERATOR_ALERTS=1` bo‘lsa, barcha guruhlardagi har bir ban va ovozsizlantirish guruh, akkaunt va sabab bilan operatorning shaxsiy chatiga yuboriladi.
- **Birinchi xabar + qo‘shilish vaqtidagi skanerlash** — profillar a’zo qo‘shilganda ham, birinchi xabarini yozganda ham tekshiriladi, shuning uchun ochiq guruhlarga havola orqali kirganlar ham nazoratda bo‘ladi.
- **Admin asboblari** — `/ban`, `/mute`, kalit so‘zlarni o‘rgatish, akkauntni belgilash va noto‘g‘ri tasniflash bo‘yicha teskari aloqa — barchasi Telegram’ning o‘zida.
- **Foydalanish va faollik hisoboti** — `/tokens` Gemini tokenlari sarfi va narxini ko‘rsatadi; `/stats` guruhlar ro‘yxati, har bir guruhda AI haqiqatan ishlayotgani va tutilgan spam haqida ma’lumot beradi; operatorga har kuni ertalab hisobot yuboriladi.
- **Tabiatan tartibli** — botning o‘z bildirishnomalari va admin buyruqlari bir necha soniyadan so‘ng guruhdan avtomatik o‘chiriladi.

## 🧠 Qanday ishlaydi

Himoyalangan guruhdagi har bir xabar arzondan qimmatga qarab boruvchi zanjir orqali o‘tadi; birinchi mos kelgan qoida ishga tushadi:

1. **Profilni skanerlash (har bir a’zo uchun bir marta)** — qo‘shilganda va birinchi xabarda.
   - Aniq behayo rasm (NudeNet) yoki 18+ kontentga havola bergan bio → **ban + o‘chirish**.
   - Aks holda bio AI qatlamiga (4-qadam) yuboriladi; 18+ degan xulosa → 24 soat ovozsiz.
2. **Fishing havolalarni tekshirish** — avval yashirin havolalar (bepul), keyin kalit bo‘lsa VirusTotal domen reytingi. Bu AI’dan oldin ishlaydi, shuning uchun fishing xabar Gemini chaqiruviga pul sarflatmaydi.
3. **Kalit so‘z qatlami (bepul)** — faqat guruh adminlari `/teach` bilan o‘rgatgan so‘zlar. Boshlang‘ich ro‘yxat o‘zi hech narsani bloklamaydi.
4. **AI qatlami** — guruhda AI yoqilgan bo‘lsa (`/ai`) va kalit mavjud bo‘lsa ishlaydi: avval guruhning o‘z kaliti, bo‘lmasa operatorning umumiy kaliti. Gemini (standart `gemini-3.1-flash-lite`) faqat 18+ kontentni baholaydi. Xarajatni nazorat qilish uchun so‘rovlar soni cheklangan.

Hamma narsa har bir guruh uchun alohida ishlaydi va bot `/enable` berilmagan guruhlarda mutlaqo jim turadi.

**Maxfiylik:** Gemini kalitlari (guruhniki ham, umumiysi ham) Fernet yordamida shifrlab saqlanadi. Xabar matni Google Gemini’ga faqat AI yoqilgan guruhlarda yuboriladi. Havolalarning domeni VirusTotal’ga faqat kalit o‘rnatilganda yuboriladi — xabarning o‘zi hech qachon. Spam-hisobot matnlari va foydalanish qatorlari 90 kundan keyin o‘chiriladi.

## 🛠️ O‘rnatish va joylashtirish

Bot bitta long-polling ishchi jarayoni va kalit kiritish shakli uchun kichik veb-endpoint sifatida ishlaydi. Joylashtirishning ikki yo‘li bor:

- **Docker, istalgan server** — `docker compose up -d --build` botni Python 3.11 va alohida PostgreSQL bilan ishga tushiradi. [deploy/README.md](deploy/README.md) ga qarang.
- **Railway** — [DEPLOY.md](DEPLOY.md) ga qarang.

### 1. Botni yaratish
Telegram’da [@BotFather](https://t.me/BotFather) bilan bog‘laning: `/newbot`, so‘ngra **maxfiylik rejimini o‘chiring** (`/setprivacy` → Disable), shunda bot guruh xabarlarini o‘qiy oladi. Bu rejim bot guruhga qo‘shilgan paytdagi holatida qotib qoladi — keyin o‘zgartirsangiz, botni guruhdan chiqarib qayta qo‘shing.

### 2. Klonlash va o‘rnatish
```bash
git clone https://github.com/SarvarVakhobov/killspam-bot.git
cd killspam-bot
pip install -r requirements.txt
```

### 3. Muhitni sozlash
`.env.example` faylini `.env` ga nusxalang va to‘ldiring:

| O‘zgaruvchi | Majburiy | Tavsifi |
|---|---|---|
| `BOT_TOKEN` | ✅ | @BotFather’dan olingan Telegram bot tokeni |
| `DATABASE_URL` | ✅ | PostgreSQL ulanish qatori |
| `ADMIN_TELEGRAM_IDS` | ✅ | Vergul bilan ajratilgan operator ID-lari (tizim ogohlantirishlari, `/stats`, `/ai`, `/globalkey`) |
| `KEY_ENCRYPTION_SECRET` | ✅ | Saqlanadigan Gemini kalitlarini shifrlash uchun Fernet kaliti. Yaratish: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. O‘zgartirmang — almashsa, saqlangan kalitlar ochilmay qoladi |
| `BASE_URL` | ✅ | Botning veb-manzili (`/setkey` va `/globalkey set` havolalarini yaratadi); havolani ochadigan odamga ochilishi kerak |
| `GEMINI_MODEL` | ➖ | AI moderatsiya uchun Gemini modeli (standart `gemini-3.1-flash-lite`). Google modelni yopsa, shu yerda almashtiring |
| `GEMINI_PRICE_IN` / `GEMINI_PRICE_OUT` | ➖ | `/tokens` narx hisobi uchun $/1 mln token (standart `0.30` / `2.50` — flash narxlari; modelingizning haqiqiy narxini qo‘ying) |
| `OPERATOR_ALERTS` | ➖ | `1` — har bir ban/ovozsizlantirish operatorga ham yuboriladi (standart `0`) |
| `VIRUSTOTAL_API_KEY` | ➖ | VirusTotal havola tekshiruvini yoqadi (bepul kalit: virustotal.com → profil → API key; daqiqasiga 4, kuniga 500 so‘rov). Yashirin havola tekshiruvi kalitsiz ham ishlaydi |
| `VT_MALICIOUS_THRESHOLD` | ➖ | Bot choralar ko‘rishi uchun domenni nechta antivirus zararli deb bilishi kerak (standart `2`) |
| `REPORT_HOUR` | ➖ | Ertalabki hisobot soati (Asia/Tashkent) (standart `9`) |
| `MAX_GROUPS_PER_OWNER` | ➖ | Suiiste’moldan himoya: operator bo‘lmagan bitta foydalanuvchi `/enable` qila oladigan guruhlar soni (standart `20`) |

> ⚠️ Haqiqiy `.env` faylingizni hech qachon commit qilmang. U gitignore qilingan — shundayligicha qoldiring.

### 4. Joylashtirish
Docker bilan — [deploy/README.md](deploy/README.md) bo‘yicha. Railway’da loyiha yarating, PostgreSQL plaginini qo‘shing, yuqoridagi o‘zgaruvchilarni o‘rnating va joylashtiring. Ikkala holatda ham ishga tushirish buyrug‘i (`Procfile`’ga qarang):
```bash
python init_db.py && python -m spam_bot.main
```
`init_db.py` har bir ishga tushishda jadvallarni yaratadi va migratsiya qiladi. Mahalliy kompyuterda ham shu ikki buyruqni bajarishingiz mumkin.

### 5. Guruhni himoya qilish
1. Botni guruhingizga qo‘shing va **Xabarlarni o‘chirish** + **Foydalanuvchilarni bloklash** huquqlari bilan **admin** qiling.
2. Guruh ichida `/enable` buyrug‘ini bering.
3. AI uchun: yoki guruhda `/setkey` bering (guruhning o‘z Gemini kaliti), yoki operator sifatida botga shaxsiy chatda `/globalkey set` yuborib umumiy kalit o‘rnating.
4. Operator sifatida botga `/ai` yuborib, AI qaysi guruhlarda ishlashini tanlang.

> ⚠️ AI barcha guruhlar uchun **standart holatda yoqilgan**. Botingizni umumiy kalit bilan ommaga ochsangiz, begonalar qo‘shgan guruhlar ham shu kalitdan foydalanadi. `/ai` da standartni o‘chirib, AI’ni faqat o‘zingiz tanlagan guruhlarda yoqing.

### Oldingi holatga qaytarish (Rollback)
Har bir reliz git tegi (`vX.Y.Z`) hisoblanadi. Orqaga qaytarish uchun oldingi tegni qayta joylashtiring; baza sxemasi faqat qo‘shiladi, shuning uchun eski kod yangi baza bilan ishlayveradi.

## 💬 Buyruqlar

| Buyruq | Kim uchun | Vazifasi |
|---|---|---|
| `/enable` · `/disable` | Guruh adminlari | Guruh himoyasini yoqish/o‘chirish |
| `/setkey` | Guruh adminlari | Guruhning o‘z Gemini kalitini saqlash (shaxsiy, bir martalik havola) |
| `/ban` · `/mute` | Guruh adminlari | Javob berilgan (reply) foydalanuvchini moderatsiya qilish |
| `/tokens` | Guruh adminlari / operator | Gemini tokenlari sarfi + narxi (kecha / 7 kun / 30 kun) |
| `/stats` | Operator (shaxsiy chat) | Guruhlar ro‘yxati (AI holati bilan) + spam/ban faolligi |
| `/ai` | Operator (shaxsiy chat) | AI’ni barcha guruhlarda yoki bittalab yoqish/o‘chirish |
| `/globalkey` | Operator (shaxsiy chat) | Umumiy kalit holati; `set` — kaliti yo‘q guruhlar uchun o‘rnatish, `off` — o‘chirish |
| `/help` · `/privacy` | Hamma | Foydalanish qo‘llanmasi / ma’lumotlar siyosati |

## 🧰 Texnologiyalar to‘plami

Python 3.11 · [aiogram 3](https://docs.aiogram.dev/) · SQLAlchemy 2 + PostgreSQL · Google Gemini (`gemini-3.1-flash-lite`; guruh kaliti yoki umumiy kalit) · [NudeNet](https://github.com/notAI-tech/NudeNet) (mahalliy NSFW modeli) · [VirusTotal API v3](https://docs.virustotal.com/reference/overview) · aiohttp · Docker.

## 📄 Litsenziya

[PolyForm Noncommercial License 1.0.0](LICENSE) litsenziyasi asosida litsenziyalangan. Siz undan har qanday **notijorat maqsadlarda** erkin foydalanishingiz, o‘zgartirishingiz va baham ko‘rishingiz mumkin. **Tijorat maqsadlarida foydalanishga ruxsat berilmaydi.**

## 🙌 Mualliflar

**[@ertagakech](https://t.me/ertagakech)** Telegram kanali uchun yaratilgan. Sun’iy intellekt haqida ko‘proq bilish uchun qo‘shiling 👉 **https://t.me/ertagakech**
