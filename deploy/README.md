# Serverga joylash

Ikki yo'l bor. **Qaysi birini tanlash hostga bog'liq — xohishga emas.**

| Host qanday | Yo'l |
|---|---|
| Python 3.11/3.12 bor **va** 5432 porti bo'sh | `deploy/install.sh` (nativ + systemd) |
| Python 3.13+ yoki 5432 band | `docker-compose.yml` (**SERVER_IP shu holatda**) |

`install.sh` boshida shu ikki shartni o'zi tekshiradi va mos kelmasa
ishlamay to'xtaydi — o'rtada qulab qolmaydi.

---

## Docker yo'li (SERVER_IP uchun ishlatilgan)

### Nega aynan Docker

Ubuntu 26.04 da faqat **Python 3.14** bor. `aiogram==3.13.0` esa
`aiohttp<3.11` va `pydantic<2.9` ni talab qiladi, bu paketlar Python 3.14 uchun
wheel chiqarmagan (`aiohttp` da cp314 faqat 3.13.0 dan boshlanadi). Natijada
nativ o'rnatish `ResolutionImpossible` bilan tugaydi.

`Dockerfile` `python:3.11-slim` ni qotirib qo'yadi — bu lokalda 120 ta test
bilan tasdiqlangan aynan o'sha muhit, shuning uchun `requirements.txt` ni
o'zgartirish shart emas.

Ikkinchi sabab: serverda 5432 portini boshqa loyihaning postgres konteyneri
egallagan. `docker-compose.yml` bazaning host portini **umuman ochmaydi** —
bot unga ichki tarmoq orqali `db` nomi bilan ulanadi, shuning uchun to'qnashuv
bo'lmaydi.

### O'rnatish

```bash
# 1. Kodni ko'chirish (GitHub'dan EMAS — pastdagi ogohlantirishga qarang)
tar czf /tmp/src.tgz --exclude=.git --exclude=.venv --exclude=logs --exclude=.env .
scp /tmp/src.tgz user@SERVER_IP:/tmp/
ssh user@SERVER_IP 'sudo mkdir -p /opt/killspam-bot && \
  sudo chown $USER /opt/killspam-bot && cd /opt/killspam-bot && tar xzf /tmp/src.tgz'

# 2. .env yaratish (600 huquq bilan!) — namuna uchun .env.example ga qarang.
#    DATABASE_URL host sifatida "db" ni ishlatadi va sslmode=disable bilan tugaydi.
#    DB_PASSWORD compose uchun alohida kerak.

# 3. Ko'tarish
ssh user@SERVER_IP 'cd /opt/killspam-bot && docker compose up -d --build'
```

### `.env` da diqqat qilinadigan qatorlar

```
DATABASE_URL=postgresql://spam:<parol>@db:5432/spam_bot_db?sslmode=disable
DB_PASSWORD=<yuqoridagi bilan bir xil parol>
BASE_URL=http://SERVER_IP:8090
PORT=8090
GEMINI_MODEL=gemini-3.1-flash-lite
```

- `sslmode=disable` **shart**: `spam_bot/db/session.py` faqat `localhost`,
  `127.0.0.1` va `.railway.internal` ni "lokal" deb biladi; compose xizmati
  `db` bu ro'yxatga tushmaydi, shuning uchun kod `sslmode=require` qo'yardi,
  oddiy postgres konteynerida esa SSL yo'q. URL'da aniq ko'rsatilgan qiymat
  evristikadan ustun turadi. Trafik Docker'ning ichki tarmog'idan chiqmaydi.
- `KEY_ENCRYPTION_SECRET` ni **hech qachon o'zgartirmang**. U almashsa,
  bazadagi shifrlangan Gemini kalitlari ochilmay qoladi va har bir guruh
  `/setkey` ni qaytadan qilishga majbur bo'ladi.

### Bazani ko'chirish (ixtiyoriy)

Guruh sozlamalari va shifrlangan kalitni saqlab qolish uchun:

```bash
pg_dump -U spam -d spam_bot_db --no-owner --no-privileges > killspam.sql
scp killspam.sql user@SERVER_IP:/tmp/
ssh user@SERVER_IP \
  'docker exec -i killspam-db psql -U spam -d spam_bot_db < /tmp/killspam.sql && shred -u /tmp/killspam.sql'
```

`KEY_ENCRYPTION_SECRET` eskisi bilan bir xil bo'lsa, kalitlar o'z-o'zidan ishlaydi.

---

## ⚠️ GitHub'dagi kod eskirgan

`install.sh` ichidagi `REPO` upstream'ga ishora qiladi, u yerdagi
`spam_bot/handlers/spam_detector.py` hali ham `gemini-2.5-flash` ni qotirib
yozgan. Bu model yangi API kalitlar uchun yopilgan va har chaqiruvda 404
qaytaradi — natijada AI **jimgina** o'chadi, faqat regex qatlami qoladi va
tashqaridan hammasi joyidadek ko'rinadi.

Tuzatish hozircha faqat lokal ish katalogida. Shuning uchun yuqorida kod
GitHub'dan emas, to'g'ridan-to'g'ri ko'chiriladi. `git push` qilinmaguncha
`install.sh` dagi `git clone` yo'lidan foydalanmang.

---

## Faqat bitta nusxa ishlashi kerak

Bitta bot tokenini bir vaqtda ikkita jarayon so'ray olmaydi — ikkinchisi
Telegram'dan `409 Conflict: terminated by other getUpdates request` oladi.
Serverni ko'targandan keyin lokal (Windows) nusxani albatta to'xtating.

Tekshirish uchun `getUpdates` ni qo'lda chaqirmang: u ishlab turgan botning
so'rovini uzib qo'yadi va poll'lar orasidagi bo'shliqqa tushib, noto'g'ri
"konflikt yo'q" natijasini beradi. Buning o'rniga logga qarang:

```bash
docker logs killspam-bot | grep -E 'Run polling|Conflict'
```

---

## Kundalik buyruqlar

```bash
cd /opt/killspam-bot
docker compose ps                 # holat
docker compose logs -f bot        # jonli log
docker compose restart bot        # qayta ishga tushirish
docker compose up -d --build bot  # kod yangilangandan keyin
curl -s http://SERVER_IP:8090/health
```

Konteynerlar `restart: unless-stopped` bilan ishlaydi va Docker boot'da
yoqilgan, shuning uchun qulash ham, server qayta yuklanishi ham botni
to'xtatmaydi. Buni sinash uchun konteyner ichidagi python jarayonini o'ldiring
(`docker kill` **emas** — uni Docker qo'lda to'xtatish deb hisoblaydi va
restart siyosatini qo'llamaydi).

## `/setkey` haqida

`BASE_URL` LAN manzili. `/setkey` havolasi faqat shu tarmoqdagi qurilmalarda
ochiladi — mobil internetdan ishlamaydi. Tashqaridan kerak bo'lsa domen va
HTTPS (reverse proxy) qo'shish lozim.
