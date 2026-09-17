"""User-facing bot copy, bilingual (Uzbek first, English below).
Uzbek produced via the team's translate.py — edit English in tasks/bot_copy_en.md
and re-translate rather than hand-editing the Uzbek. Kept generic on purpose
(no content-type specifics)."""

_SEP = "\n\n———\n\n"

_UZ_START = """🛡 Spamdan himoya boti

Spam va keraksiz xabarlarni avtomatik o'chirish orqali guruhingiz tozaligini saqlashga yordam beraman.

Tezkor boshlash:
1. Meni guruhingizga qo'shing.
2. Meni admin qiling ("Xabarlarni o'chirish" va "Foydalanuvchilarni bloklash" huquqlari bilan).
3. Guruh ichida /enable buyrug'ini yuboring.

Bo'ldi — himoyani boshlayman. To'liq qo'llanma uchun /help deb yozing."""

_EN_START = """🛡 Spam Protection Bot

I help keep your group clean by automatically removing spam and unwanted messages.

Quick start:
1. Add me to your group.
2. Make me an admin (with "Delete messages" and "Ban users").
3. Run /enable inside the group.

That's it — I'll start protecting it. Type /help for the full guide."""

_UZ_HELP = """🛡 Mendan qanday foydalanish kerak

Men avtomatik ravishda nimalarni o'chiraman:
• 18+ fake akkauntlar: behayo profil rasmi yoki 18+ kontentga havola bergan bio → ban. AI shahvoniy deb topgan xabar yoki bio → o'chiriladi, yuborgan odam 24 soat ovozsiz qilinadi.
• Xavfli havolalar: VirusTotal zararli deb bilgan saytga havola → xabar o'chiriladi, yuborgan odam ban qilinadi.
• Yashirin havolalar: bir saytni ko'rsatib, boshqasini ochadigan havola.
• Ilova yuklamalari: xabardagi .apk/.exe fayllar yoki ularga havolalar va bio'dagi ilova havolalari — akkaunt o'g'irlashning keng tarqalgan usuli.
• Havolali ommaviy xabarlar: 2 daqiqa ichida 3 va undan ortiq akkauntdan kelgan bir xil havolali xabar.

Yashirin havola, ilova yuklamasi va ommaviy xabarlarda xabar o'chiriladi, yuborgan odam esa 24 soat ovozsiz qilinadi — u guruhda qoladi va o'qiy oladi, lekin yoza olmaydi. Adminlarga Ban / Unmute tugmalari bilan xabar keladi, shuning uchun xatoni bir bosishda tuzatish mumkin.

Nimalarga tegmayman: reklama, a'zoning o'z kanali havolasi, kripto haqidagi gaplar, bahslar, mavzudan tashqari suhbatlar, kino muhokamasi.

Yangi a'zolarni guruhga qo'shilganda va birinchi xabarini yozganda tekshiraman, guruhga qo'shilish so'rovlarini ham saralayman.

Sozlash:
1. Meni guruhingizga qo'shing.
2. Meni admin qiling — menga "Xabarlarni o'chirish" va "Foydalanuvchilarni bloklash" huquqlari kerak.
3. Guruh ichida /enable buyrug'ini yuboring.
4. Ixtiyoriy: /setkey — o'z Gemini kalitingiz bilan AI orqali aniqlash; /setvtkey — o'z VirusTotal kalitingiz bilan havolalarni tekshirish. Kalitlar shifrlab saqlanadi. Ularsiz ham rasm, bio, yashirin havola, ilova va ommaviy xabar tekshiruvlari ishlayveradi (bot operatori umumiy kalit ham berishi mumkin).

Admin buyruqlari (xabarga javob berish orqali):
/ban — foydalanuvchini bloklash
/mute — 24 soatga ovozsiz rejimga o'tkazish; /mute N — N soatga; sababini ko'rsatish uchun /mute <sabab> yoki /mute N <sabab>
/teach — ushbu guruh uchun o'sha spam xabardagi kalit so'zlarni o'rganish
/flag — yuboruvchining akkauntini ushbu guruh uchun shubhali bot profili sifatida belgilash
/enable — ushbu guruhni himoya qilishni boshlash
/disable — ushbu guruhni himoya qilishni to'xtatish
/setkey — Gemini kalitingiz bilan AI orqali aniqlashni yoqish
/setvtkey — VirusTotal kalitingiz bilan havolalarni tekshirish
/privacy — men qanday ma'lumotlarni saqlayman
/help — ushbu qo'llanmani ko'rsatish

Xabar berish: adminlarni ogohlantirish uchun har kim xabarga "spam", "ban" yoki "admin" so'zlari bilan javob qaytarishi mumkin.

Yangilanganimda, nimalar o'zgarganini bilishingiz uchun bu yerga reliz qaydlarini joylashtiraman.

Men faqat admin /enable buyrug'ini ishlatgan guruhlardagina ishlayman — boshqa hech qayerda emas."""

_EN_HELP = """🛡 How to use me

What I remove automatically:
• 18+ fake accounts: an explicit profile photo or a bio linking adult content → banned. A message or bio the AI finds sexual → deleted, sender muted for 24 hours.
• Dangerous links: a link to a site VirusTotal flags as malicious → deleted, sender banned.
• Disguised links: a link that shows one site but opens another.
• App downloads: .apk/.exe files or links to them in a message, and app links in a bio — a common account-stealing trick.
• Link floods: the same message with a link from 3 or more accounts within 2 minutes.

For disguised links, app downloads and link floods, the message is deleted and the sender is muted for 24 hours — they stay in the group and can read, but can't post. Admins get an alert with Ban / Unmute buttons, so a mistake is one tap to undo.

What I leave alone: ads, a member's own channel link, crypto talk, arguments, off-topic chatter, film discussion.

I check new members when they join and when they first post, and I screen join requests.

Setup:
1. Add me to your group.
2. Make me an admin — I need "Delete messages" and "Ban users".
3. Run /enable inside the group.
4. Optional: /setkey — AI detection with your own Gemini key; /setvtkey — link checks with your own VirusTotal key. Keys are stored encrypted. Without them, the photo, bio, disguised-link, app and link-flood checks still run (the bot operator may also provide shared keys).

Admin commands (reply to a message):
/ban — ban the user
/mute — mute for 24 hours; /mute N — for N hours; add a reason with /mute <reason> or /mute N <reason>
/teach — learn that spam message's keywords for this group
/flag — flag the sender's account as a suspicious bot profile for this group
/enable — protect this group
/disable — stop protecting this group
/setkey — turn on AI detection with your Gemini key
/setvtkey — check links with your VirusTotal key
/privacy — what data I store
/help — show this guide

Reporting: anyone can reply to a message with "spam", "ban", or "admin" to alert the admins.

When I'm updated, I post the release notes here so you know what changed.

I only work in groups where an admin has run /enable — nowhere else."""

START_TEXT = _UZ_START + _SEP + _EN_START
HELP_TEXT = _UZ_HELP + _SEP + _EN_HELP
# /help is sent one language per message: together they exceed Telegram's
# 4096-character message limit, and an over-long reply is rejected outright.
HELP_PARTS = (_UZ_HELP, _EN_HELP)

SETUP_EN = """👋 Thanks for adding me!

I remove 18+ fake accounts, phishing links, app scams (.apk/.exe) and link floods.

To start protecting this group:
1. Make me an admin — I need "Delete messages" and "Ban users".
2. Send /enable in the group.
3. Optional: /setkey — AI detection with your own Gemini API key (free from Google AI Studio); /setvtkey — link checks with your own VirusTotal API key (free at virustotal.com). Without keys, the photo, bio, disguised-link, app and link-flood checks still work.

Type /help for the full guide."""

_UZ_SETUP = """👋 Meni qo'shganingiz uchun rahmat!

Men 18+ fake akkauntlar, fishing havolalar, ilova firibgarliklari (.apk/.exe) va havolali ommaviy xabarlarni o'chiraman.

Ushbu guruhni himoya qilishni boshlash uchun:
1. Meni admin qiling — menga "Xabarlarni o'chirish" va "Foydalanuvchilarni bloklash" huquqlari kerak.
2. Guruhda /enable buyrug'ini yuboring.
3. Ixtiyoriy: /setkey — o'z Gemini API kalitingiz bilan AI orqali aniqlash (Google AI Studio'da bepul); /setvtkey — o'z VirusTotal API kalitingiz bilan havolalarni tekshirish (virustotal.com'da bepul). Kalitsiz ham rasm, bio, yashirin havola, ilova va ommaviy xabar tekshiruvlari ishlaydi.

To'liq qo'llanma uchun /help buyrug'ini yozing."""
SETUP_TEXT = _UZ_SETUP + _SEP + SETUP_EN


PRIVACY_EN = """🔒 Privacy

I store only what I need to moderate your group:
• the text of messages I flag as spam (auto-deleted after 90 days),
• IDs of blocked or flagged accounts and your group's settings,
• if you add a Gemini key, it is encrypted at rest and used only to classify your own group's messages.
• if your group has no key of its own, the bot operator may classify its messages with a shared Gemini key; those messages are then sent to Google Gemini for that check only.
• to catch phishing, the site address (domain) of links posted in the group may be checked with VirusTotal — never the message itself. If you add a VirusTotal key, it is encrypted at rest and used only for your group's link checks.

I never sell your data or share it outside your group's admins. Run /disable to stop moderation; contact the bot operator to remove your data."""

_UZ_PRIVACY = """🔒 Maxfiylik

Guruhingizni moderatsiya qilish uchun faqat zarur bo'lgan ma'lumotlarni saqlayman:
• spam deb belgilangan xabarlar matni (90 kundan keyin avtomatik o'chiriladi),
• bloklangan yoki belgilangan akkauntlar ID-lari va guruhingiz sozlamalari,
• agar Gemini kalitini qo'shsangiz, u saqlash vaqtida shifrlanadi va faqat guruhingiz xabarlarini tasniflash uchun ishlatiladi.
• agar guruhingizning o'z kaliti bo'lmasa, bot operatori xabarlarni umumiy Gemini kaliti bilan tasniflashi mumkin; bunda xabarlar faqat shu tekshiruv uchun Google Gemini'ga yuboriladi.
• fishingni aniqlash uchun guruhga yuborilgan havolalarning sayt manzili (domeni) VirusTotal'da tekshirilishi mumkin — xabarning o'zi hech qachon yuborilmaydi. VirusTotal kalitini qo'shsangiz, u shifrlab saqlanadi va faqat guruhingiz havolalarini tekshirish uchun ishlatiladi.

Ma'lumotlaringizni hech qachon sotmayman va guruhingiz adminlaridan tashqari hech kimga ulashmayman. Moderatsiyani to'xtatish uchun /disable buyrug'ini bering; ma'lumotlaringizni o'chirish uchun bot operatoriga murojaat qiling."""
PRIVACY_TEXT = _UZ_PRIVACY + _SEP + PRIVACY_EN

# Bot profile description (<=512 chars each), set per-locale at startup.
DESCRIPTION_UZ = "Guruhlaringizni 18+ fake akkauntlar, fishing havolalar va .apk/.exe firibgarliklaridan himoya qilaman. Ishni boshlash uchun: meni guruhingizga qo'shing, admin qiling va /enable buyrug'ini yuboring. Yo'riqnoma uchun /help deb yozing."
DESCRIPTION_EN = "I protect your group from 18+ fake accounts, phishing links and .apk/.exe scams. To start: add me to your group, make me an admin, and run /enable. Type /help for the guide."

# Command menu (command, description) per locale.
COMMANDS_UZ = [
    ("ban", "Xabariga javob berilgan foydalanuvchini bloklash"),
    ("mute", "Javob berilgan foydalanuvchining ovozini o'chirish: /mute, /mute N yoki /mute [N] <reason>"),
    ("enable", "Ushbu guruhni himoya qilish"),
    ("disable", "Guruh himoyasini to'xtatish"),
    ("setkey", "Gemini kalitingiz yordamida AI deteksiyasini yoqing"),
    ("setvtkey", "VirusTotal kalitingiz bilan havolalarni tekshirishni yoqing"),
    ("tokens", "Token sarfi: kecha, 7 kun, 30 kun (model, token, narx)"),
    ("privacy", "Bot qanday ma'lumotlarni saqlaydi"),
    ("help", "Botdan foydalanish bo'yicha qo'llanma"),
]
COMMANDS_EN = [
    ("ban", "Ban the replied-to user"),
    ("mute", "Mute replied user: /mute, /mute N, or /mute [N] <reason>"),
    ("enable", "Protect this group"),
    ("disable", "Stop protecting this group"),
    ("setkey", "Turn on AI detection with your Gemini key"),
    ("setvtkey", "Check links with your VirusTotal key"),
    ("tokens", "Token usage: yesterday, 7 days, 30 days (model, tokens, cost)"),
    ("privacy", "What data the bot stores"),
    ("help", "How to use the bot"),
]
