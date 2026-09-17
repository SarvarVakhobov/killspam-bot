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

Men avtomatik ravishda nimalar qilaman:
• Spam va istalmagan xabarlarni aniqlayman va o'chiraman — matnlarda ham, rasm tavsiflarida ham.
• Yangi a'zolar qo'shilganda ularni tekshiraman — tarjimai holi (bio) va barcha profil rasmlarini — hamda guruhga qo'shilish so'rovlarini saralayman.
• Spamerlarni avtomatik ravishda bloklayman (odamlarni 24 soatga, botlarni butunlay) va adminlarni xabardor qilaman; adminlar bu qarorni har doim bekor qilishlari mumkin.

Sozlash:
1. Meni guruhingizga qo'shing.
2. Meni admin qiling — menga "Xabarlarni o'chirish" va "Foydalanuvchilarni bloklash" huquqlari kerak.
3. Guruh ichida /enable buyrug'ini yuboring.
4. Ixtiyoriy: o'zingizning Gemini kalitingiz yordamida AI orqali aniqlashni yoqish uchun /setkey buyrug'ini yuboring. Kalitsiz ham kalit so'zlar qoidalari guruhni himoya qilaveradi.

Admin buyruqlari (xabarga javob berish orqali):
/ban — foydalanuvchini bloklash
/mute — 24 soatga ovozsiz rejimga o'tkazish; /mute N — N soatga; sababini ko'rsatish uchun /mute <sabab> yoki /mute N <sabab>
/teach — ushbu guruh uchun o'sha spam xabardagi kalit so'zlarni o'rganish
/flag — yuboruvchining akkauntini ushbu guruh uchun shubhali bot profili sifatida belgilash
/enable — ushbu guruhni himoya qilishni boshlash
/disable — ushbu guruhni himoya qilishni to'xtatish
/setkey — Gemini kalitingiz bilan AI orqali aniqlashni yoqish
/privacy — men qanday ma'lumotlarni saqlayman
/help — ushbu qo'llanmani ko'rsatish

Xabar berish: adminlarni ogohlantirish uchun har kim xabarga "spam", "ban" yoki "admin" so'zlari bilan javob qaytarishi mumkin.

Yangilanganimda, nimalar o'zgarganini bilishingiz uchun bu yerga reliz qaydlarini joylashtiraman.

Men faqat admin /enable buyrug'ini ishlatgan guruhlardagina ishlayman — boshqa hech qayerda emas."""

_EN_HELP = """🛡 How to use me

What I do automatically:
• Detect and remove spam and unwanted messages — in text and in image captions.
• Check new members when they join — their bio and all of their profile photos — and screen join requests.
• Block spammers automatically (24 hours for people, permanently for bots) and notify admins, who can always override.

Setup:
1. Add me to your group.
2. Make me an admin — I need "Delete messages" and "Ban users".
3. Run /enable inside the group.
4. Optional: run /setkey to turn on AI detection with your own Gemini key. Without one, keyword rules still protect the group.

Admin commands (reply to a message):
/ban — ban the user
/mute — mute for 24 hours; /mute N — for N hours; add a reason with /mute <reason> or /mute N <reason>
/teach — learn that spam message's keywords for this group
/flag — flag the sender's account as a suspicious bot profile for this group
/enable — protect this group
/disable — stop protecting this group
/setkey — turn on AI detection with your Gemini key
/privacy — what data I store
/help — show this guide

Reporting: anyone can reply to a message with "spam", "ban", or "admin" to alert the admins.

When I'm updated, I post the release notes here so you know what changed.

I only work in groups where an admin has run /enable — nowhere else."""

START_TEXT = _UZ_START + _SEP + _EN_START
HELP_TEXT = _UZ_HELP + _SEP + _EN_HELP

SETUP_EN = """👋 Thanks for adding me!

To start protecting this group:
1. Make me an admin — I need "Delete messages" and "Ban users".
2. Send /enable in the group.
3. Optional: run /setkey to turn on AI-powered detection with your own Gemini API key (free from Google AI Studio). Without a key I still block spam with keyword rules.

Type /help for the full guide."""

_UZ_SETUP = """👋 Meni qo'shganingiz uchun rahmat!

Ushbu guruhni himoya qilishni boshlash uchun:
1. Meni admin qiling — menga "Xabarlarni o'chirish" va "Foydalanuvchilarni bloklash" huquqlari kerak.
2. Guruhda /enable buyrug'ini yuboring.
3. Ixtiyoriy: o'zingizning Gemini API kalitingiz (Google AI Studio'dan bepul olish mumkin) yordamida sun'iy intellekt asosidagi aniqlashni yoqish uchun /setkey buyrug'ini ishga tushiring. Kalitsiz ham men kalit so'z qoidalari orqali spamni bloklayman.

To'liq qo'llanma uchun /help buyrug'ini yozing."""
SETUP_TEXT = _UZ_SETUP + _SEP + SETUP_EN


PRIVACY_EN = """🔒 Privacy

I store only what I need to moderate your group:
• the text of messages I flag as spam (auto-deleted after 90 days),
• IDs of blocked or flagged accounts and your group's settings,
• if you add a Gemini key, it is encrypted at rest and used only to classify your own group's messages.
• if your group has no key of its own, the bot operator may classify its messages with a shared Gemini key; those messages are then sent to Google Gemini for that check only.

I never sell your data or share it outside your group's admins. Run /disable to stop moderation; contact the bot operator to remove your data."""

_UZ_PRIVACY = """🔒 Maxfiylik

Guruhingizni moderatsiya qilish uchun faqat zarur bo'lgan ma'lumotlarni saqlayman:
• spam deb belgilangan xabarlar matni (90 kundan keyin avtomatik o'chiriladi),
• bloklangan yoki belgilangan akkauntlar ID-lari va guruhingiz sozlamalari,
• agar Gemini kalitini qo'shsangiz, u saqlash vaqtida shifrlanadi va faqat guruhingiz xabarlarini tasniflash uchun ishlatiladi.
• agar guruhingizning o'z kaliti bo'lmasa, bot operatori xabarlarni umumiy Gemini kaliti bilan tasniflashi mumkin; bunda xabarlar faqat shu tekshiruv uchun Google Gemini'ga yuboriladi.

Ma'lumotlaringizni hech qachon sotmayman va guruhingiz adminlaridan tashqari hech kimga ulashmayman. Moderatsiyani to'xtatish uchun /disable buyrug'ini bering; ma'lumotlaringizni o'chirish uchun bot operatoriga murojaat qiling."""
PRIVACY_TEXT = _UZ_PRIVACY + _SEP + PRIVACY_EN

# Bot profile description (<=512 chars each), set per-locale at startup.
DESCRIPTION_UZ = "Guruhlaringizni spam va keraksiz xabarlardan himoya qilaman. Ishni boshlash uchun: meni guruhingizga qo'shing, admin qiling va /enable buyrug'ini yuboring. Yo'riqnoma uchun /help deb yozing."
DESCRIPTION_EN = "I protect your group from spam and unwanted messages. To start: add me to your group, make me an admin, and run /enable. Type /help for the guide."

# Command menu (command, description) per locale.
COMMANDS_UZ = [
    ("ban", "Xabariga javob berilgan foydalanuvchini bloklash"),
    ("mute", "Javob berilgan foydalanuvchining ovozini o'chirish: /mute, /mute N yoki /mute [N] <reason>"),
    ("enable", "Ushbu guruhni himoya qilish"),
    ("disable", "Guruh himoyasini to'xtatish"),
    ("setkey", "Gemini kalitingiz yordamida AI deteksiyasini yoqing"),
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
    ("tokens", "Token usage: yesterday, 7 days, 30 days (model, tokens, cost)"),
    ("privacy", "What data the bot stores"),
    ("help", "How to use the bot"),
]
