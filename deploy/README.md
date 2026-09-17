# Serverga joylash

Ikki yo'l bor. **Qaysi birini tanlash hostga bog'liq — xohishga emas.**

| Host qanday | Yo'l |
|---|---|
| Python 3.11/3.12 bor **va** 5432 porti bo'sh | `deploy/install.sh` (nativ + systemd) |
| Python 3.13+ (masalan Ubuntu 26.04) yoki 5432 band | `docker-compose.yml` — **tavsiya etiladi** |

`install.sh` boshida shu ikki shartni o'zi tekshiradi va mos kelmasa ishlamay
to'xtaydi — o'rtada qulab qolmaydi.

---

## Docker yo'li

### Nega Docker

Yangi Ubuntu (26.04) da faqat **Python 3.14** bor. `aiogram==3.13.0` esa
`aiohttp<3.11` va `pydantic<2.9` ni talab qiladi, bu paketlar Python 3.14 uchun
wheel chiqarmagan (`aiohttp` da cp314 faqat 3.13.0 dan boshlanadi), shuning uchun
nativ o'rnatish `ResolutionImpossible` bilan tugaydi.

`Dockerfile` `python:3.11-slim` ni qotirib qo'yadi — testlar ishlaydigan aynan
o'sha muhit, shuning uchun `requirements.txt` ni o'zgartirish shart emas.

`docker-compose.yml` bazaning host portini **umuman ochmaydi**: bot bazaga ichki
tarmoq orqali `db` nomi bilan ulanadi. Serverda boshqa PostgreSQL 5432 ni
egallagan bo'lsa ham to'qnashuv bo'lmaydi.

### O'rnatish

```bash
git clone https://github.com/SarvarVakhobov/killspam-bot.git /opt/killspam-bot
cd /opt/killspam-bot
cp .env.example .env && chmod 600 .env    # to'ldiring — pastga qarang
docker compose up -d --build
curl -s http://localhost:8090/health       # {"status": "ok", ...}
```

### `.env` da diqqat qilinadigan qatorlar

```
DATABASE_URL=postgresql://spam:<parol>@db:5432/spam_bot_db?sslmode=disable
DB_PASSWORD=<yuqoridagi bilan bir xil parol>
BASE_URL=http://SERVER_IP:8090
PORT=8090
GEMINI_MODEL=gemini-3.1-flash-lite
OPERATOR_ALERTS=1                 # ixtiyoriy: har bir ban operatorga ham keladi
VIRUSTOTAL_API_KEY=<kalit>        # ixtiyoriy: server bo'yicha zaxira VirusTotal kaliti
VT_MALICIOUS_THRESHOLD=2
```

- `sslmode=disable` **shart**: `spam_bot/db/session.py` faqat `localhost`,
  `127.0.0.1` va `.railway.internal` ni "lokal" deb biladi. Compose xizmati `db`
  bu ro'yxatga kirmaydi, shuning uchun kod `sslmode=require` qo'yardi, oddiy
  postgres konteynerida esa SSL yo'q. URL'da aniq ko'rsatilgan qiymat
  evristikadan ustun turadi. Trafik Docker'ning ichki tarmog'idan chiqmaydi.
- `KEY_ENCRYPTION_SECRET` ni **hech qachon o'zgartirmang**. U almashsa, bazadagi
  shifrlangan Gemini kalitlari ochilmay qoladi va har bir guruh `/setkey` ni
  qaytadan qilishga majbur bo'ladi.
- `.env` ni o'zgartirgandan keyin `docker compose restart` **yetmaydi** —
  o'zgaruvchilar konteyner yaratilganda yoziladi. `docker compose up -d bot`
  ishlating.
- `BASE_URL` — `/setkey` va `/globalkey set` havolalari shu manzilga ochiladi.
  LAN manzili bo'lsa, havola faqat shu tarmoqdagi qurilmalarda ochiladi.
  Tashqaridan kerak bo'lsa domen va HTTPS (reverse proxy) qo'shing.

### Bazani ko'chirish (ixtiyoriy)

Guruh sozlamalari va shifrlangan kalitlarni boshqa serverdan saqlab qolish uchun:

```bash
pg_dump -U spam -d spam_bot_db --no-owner --no-privileges > killspam.sql
scp killspam.sql user@SERVER_IP:/tmp/
ssh user@SERVER_IP \
  'docker exec -i killspam-db psql -U spam -d spam_bot_db < /tmp/killspam.sql && shred -u /tmp/killspam.sql'
```

`KEY_ENCRYPTION_SECRET` eskisi bilan bir xil bo'lsa, kalitlar o'z-o'zidan ishlaydi.

---

## Yangilash

```bash
cd /opt/killspam-bot
docker exec killspam-db pg_dump -U spam -d spam_bot_db > "backup-$(date +%F).sql"   # zaxira
git pull
docker compose up -d --build bot
docker compose logs --tail 20 bot
```

Bazaga yangi ustunlar kerak bo'lsa, `init_db.py` ularni bot ishga tushganda o'zi
qo'shadi.

> Asl repo (`anvarnarz/killspam-bot`) hali ham `gemini-2.5-flash` ni qotirib
> yozgan — bu model yangi API kalitlar uchun yopilgan, AI jimgina o'chib qoladi.
> Shu fork'dan (`https://github.com/SarvarVakhobov/killspam-bot`) oling.

## Operator sozlamalari

Bot ishga tushgach, `ADMIN_TELEGRAM_IDS` dagi akkauntdan botga **shaxsiy chatda**:

- `/globalkey set` — kaliti yo'q guruhlar uchun umumiy Gemini kaliti (bir martalik havola orqali).
- `/globalvtkey set` — kaliti yo'q guruhlar uchun umumiy VirusTotal kaliti. Guruh adminlari `/setvtkey`
  bilan o'z kalitini qo'shishi mumkin; hech biri bo'lmasa `.env` dagi `VIRUSTOTAL_API_KEY` ishlatiladi.
  Bepul limit bitta kalitga kuniga 500 so'rov — guruhlar ko'paysa, o'z kalitlari bo'lgani ma'qul.
- `/ai` — AI qaysi guruhlarda ishlashi: hammasida, hech birida yoki bittalab.

> ⚠️ AI standart holatda **barcha** guruhlarda yoqilgan. Botni ommaga ochib, umumiy
> kalit o'rnatsangiz, begonalar qo'shgan guruhlar ham shu kalit hisobidan ishlaydi.
> `/ai` da standartni o'chirib, kerakli guruhlarni alohida yoqing. Sarfni `/tokens`
> da ko'rasiz.

---

## Faqat bitta nusxa ishlashi kerak

Bitta bot tokenini bir vaqtda ikkita jarayon so'ray olmaydi — ikkinchisi
Telegram'dan `409 Conflict: terminated by other getUpdates request` oladi. Yangi
serverni ko'targandan keyin eski nusxani albatta to'xtating.

Tekshirish uchun `getUpdates` ni qo'lda chaqirmang: u ishlab turgan botning
so'rovini uzib qo'yadi va poll'lar orasidagi bo'shliqqa tushib, noto'g'ri
"konflikt yo'q" natijasini berishi mumkin. Buning o'rniga logga qarang:

```bash
docker logs killspam-bot | grep -E 'Run polling|Conflict'
```

## Kundalik buyruqlar

```bash
cd /opt/killspam-bot
docker compose ps                 # holat
docker compose logs -f bot        # jonli log
docker compose restart bot        # qayta ishga tushirish (.env o'zgarmagan bo'lsa)
docker compose up -d --build bot  # kod yoki .env yangilangandan keyin
curl -s http://SERVER_IP:8090/health
```

## Doimiy ishlash

Konteynerlar `restart: unless-stopped` bilan ishlaydi. Docker ham boot'da yoqilgan
bo'lsa (`systemctl is-enabled docker`), qulash ham, server qayta yuklanishi ham
botni to'xtatmaydi. Server yonayotganda bot bazadan oldin ishga tushib qolsa, u bir
necha marta qulab, baza tayyor bo'lgach o'zi tiklanadi.

Bitta istisno: `docker stop` yoki `docker compose stop` qilingan konteynerni
`unless-stopped` "qasddan to'xtatilgan" deb hisoblaydi va qayta yuklangandan keyin
ham ko'tarmaydi. Keyin `docker compose up -d` bilan qaytaring.

Tiklanishni sinash uchun konteyner ichidagi python jarayonini o'ldiring —
`docker kill` **emas**: uni Docker qo'lda to'xtatish deb hisoblaydi va restart
siyosatini qo'llamaydi.
