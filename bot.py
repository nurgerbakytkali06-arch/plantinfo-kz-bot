import asyncio
import json
import os
import re
import sqlite3
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from dotenv import load_dotenv

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_NAME = os.getenv("BOT_GROUP", "ХБ-31").strip()
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL", "https://plantinfo-kz-bot.onrender.com/webhook"
).rstrip("/")

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "plants_kk.json"
if not DATA_FILE.exists():
    DATA_FILE = BASE / "plants_kk.json"
IMAGE_DIR = BASE / "images"
DB_FILE = BASE / "translations.sqlite3"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env файлына енгізілуі керек.")

with DATA_FILE.open("r", encoding="utf-8") as f:
    PLANTS = json.load(f)

PLANT_BY_ID = {int(p["id"]): p for p in PLANTS}

CATEGORIES = {
    "trees": range(1, 25),
    "flowers": range(25, 66),
    "field": range(66, 101),
    "lower": range(101, 116),
}

TEXT = {
    "kk": {
        "choose_lang": "🌐 Тілді таңдаңыз:",
        "welcome": "🌿 Өсімдіктер энциклопедиясы",
        "hello": "Сәлем! Ботқа қош келдіңіз.",
        "menu": "🌿 Өсімдіктер энциклопедиясы\n\nҚажетті бөлімді таңдаңыз:",
        "plants": "🌱 Өсімдіктер",
        "trees": "🌳 Ағаштар мен бұталар",
        "flowers": "🌸 Гүлді және шөптесін өсімдіктер",
        "field": "🌾 Дала және ауылшаруашылық өсімдіктері",
        "lower": "🌿 Мүк, плаун және қырықжапырақтәрізділер",
        "search": "🔎 Іздеу",
        "about": "ℹ️ Бот туралы",
        "language": "🌐 Тілді өзгерту",
        "back": "🔙 Артқа",
        "menu_back": "🏠 Негізгі мәзір",
        "choose_plant": "Өсімдікті таңдаңыз:",
        "search_help": "🔎 Өсімдіктің қазақша немесе латынша атауын жазыңыз:\nМысалы: Қарағайлы шырша",
        "not_found": "Өсімдік табылмады.",
        "about_text": "Бұл бот берілген оқу материалдары негізінде 115 өсімдік туралы ақпаратты қарауға арналған.\n\nТоп: ХБ-31",
        "source": "Дереккөз: берілген оқу материалдары.",
        "no_text": "Бұл түр бойынша бастапқы материалда толық сипаттама мәтіні берілмеген.",
        "translate_busy": "⏳ Ақпарат дайындалып жатыр...",
    },
    "ru": {
        "choose_lang": "🌐 Выберите язык:",
        "welcome": "🌿 Энциклопедия растений",
        "hello": "Здравствуйте! Добро пожаловать в бот.",
        "menu": "🌿 Энциклопедия растений\n\nВыберите нужный раздел:",
        "plants": "🌱 Растения",
        "trees": "🌳 Деревья и кустарники",
        "flowers": "🌸 Цветковые и травянистые растения",
        "field": "🌾 Полевые и сельскохозяйственные растения",
        "lower": "🌿 Мхи, плауны и папоротникообразные",
        "search": "🔎 Поиск",
        "about": "ℹ️ О боте",
        "language": "🌐 Сменить язык",
        "back": "🔙 Назад",
        "menu_back": "🏠 Главное меню",
        "choose_plant": "Выберите растение:",
        "search_help": "🔎 Введите казахское или латинское название растения:\nНапример: Қарағайлы шырша",
        "not_found": "Растение не найдено.",
        "about_text": "Этот бот предназначен для просмотра информации о 115 растениях на основе предоставленных учебных материалов.\n\nГруппа: ХБ-31",
        "source": "Источник: предоставленные учебные материалы.",
        "no_text": "В исходном материале нет полного текстового описания этого вида.",
        "translate_busy": "⏳ Подготавливаем информацию...",
    },
    "en": {
        "choose_lang": "🌐 Choose a language:",
        "welcome": "🌿 Plant Encyclopedia",
        "hello": "Hello! Welcome to the bot.",
        "menu": "🌿 Plant Encyclopedia\n\nChoose a section:",
        "plants": "🌱 Plants",
        "trees": "🌳 Trees and shrubs",
        "flowers": "🌸 Flowering and herbaceous plants",
        "field": "🌾 Field and agricultural plants",
        "lower": "🌿 Mosses, clubmosses and ferns",
        "search": "🔎 Search",
        "about": "ℹ️ About the bot",
        "language": "🌐 Change language",
        "back": "🔙 Back",
        "menu_back": "🏠 Main menu",
        "choose_plant": "Choose a plant:",
        "search_help": "🔎 Enter the Kazakh or Latin name of the plant:\nExample: Қарағайлы шырша",
        "not_found": "Plant not found.",
        "about_text": "This bot is designed to browse information about 115 plants based on the provided educational materials.\n\nGroup: ХБ-31",
        "source": "Source: provided educational materials.",
        "no_text": "The supplied source material does not contain a full textual description for this species.",
        "translate_busy": "⏳ Preparing information...",
    },
}

# Keep translations cached locally so the same plant is not translated repeatedly.
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT NOT NULL)")
conn.execute(
    """CREATE TABLE IF NOT EXISTS translations (
        plant_id INTEGER,
        lang TEXT,
        name TEXT,
        body TEXT,
        PRIMARY KEY (plant_id, lang)
    )"""
)
conn.commit()


def get_lang(user_id: int) -> str:
    row = conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else "kk"


def set_lang(user_id: int, lang: str) -> None:
    conn.execute(
        "INSERT INTO users(user_id,lang) VALUES(?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
        (user_id, lang),
    )
    conn.commit()


def safe_edit(message: Message, text: str, reply_markup=None) -> None:
    # Defined async below; this wrapper is only for type/structure clarity.
    raise RuntimeError


async def edit_message(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _translate_block(text: str, target: str) -> str:
    if not text or target == "kk" or GoogleTranslator is None:
        return text

    # Translate in moderate chunks; avoid sending the entire long document at once.
    paragraphs = text.split("\n\n")
    chunks = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) > 2800 and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = candidate
    if buf:
        chunks.append(buf)

    translated_chunks = []
    for chunk in chunks:
        try:
            translated_chunks.append(
                GoogleTranslator(source="kk", target=target).translate(chunk)
            )
        except Exception:
            translated_chunks.append(chunk)
    return "\n\n".join(translated_chunks)


async def translated(plant: dict, lang: str):
    if lang == "kk":
        return plant["name_kk"], plant["source_kk"]

    row = conn.execute(
        "SELECT name,body FROM translations WHERE plant_id=? AND lang=?",
        (int(plant["id"]), lang),
    ).fetchone()
    if row:
        return row

    # Run the blocking translator off the event loop.
    name, body = await asyncio.to_thread(
        lambda: (
            _translate_block(plant["name_kk"], lang),
            _translate_block(plant["source_kk"], lang),
        )
    )
    conn.execute(
        "INSERT OR REPLACE INTO translations(plant_id,lang,name,body) VALUES(?,?,?,?)",
        (int(plant["id"]), lang, name, body),
    )
    conn.commit()
    return name, body


def image_for(plant_id: int):
    stem = f"plant_{plant_id:03d}"
    if IMAGE_DIR.exists():
        matches = sorted(IMAGE_DIR.glob(stem + ".*"))
        if matches:
            return matches[0]
    matches = sorted(BASE.glob(stem + ".*"))
    return matches[0] if matches else None


def language_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang:kk")],
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
        ]
    )


def main_menu(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["plants"], callback_data="plants")],
            [InlineKeyboardButton(text=TEXT[lang]["search"], callback_data="search")],
            [InlineKeyboardButton(text=TEXT[lang]["about"], callback_data="about")],
            [InlineKeyboardButton(text=TEXT[lang]["language"], callback_data="language")],
        ]
    )


def category_menu(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["trees"], callback_data="cat:trees")],
            [InlineKeyboardButton(text=TEXT[lang]["flowers"], callback_data="cat:flowers")],
            [InlineKeyboardButton(text=TEXT[lang]["field"], callback_data="cat:field")],
            [InlineKeyboardButton(text=TEXT[lang]["lower"], callback_data="cat:lower")],
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")],
        ]
    )


def category_keyboard(category: str, lang: str):
    # Important performance fix: do NOT translate all 24/41/35/15 names here.
    # That was the main reason category/search navigation became slow.
    rows = []
    for pid in CATEGORIES[category]:
        p = PLANT_BY_ID[int(pid)]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{pid}. {p['name_kk'][:45]}",
                    callback_data=f"plant:{pid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="plants")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plant_markup(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["plants"], callback_data="plants")],
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")],
        ]
    )


def chunks(text: str, limit: int = 3900):
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < 500:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip()
    if text:
        yield text


async def send_plant(bot: Bot, chat_id: int, plant_id: int, lang: str):
    plant = PLANT_BY_ID[plant_id]
    name, body = await translated(plant, lang)
    body = body.strip() or TEXT[lang]["no_text"]
    group_label = {"kk": "Топ", "ru": "Группа", "en": "Group"}[lang]
    source = TEXT[lang]["source"]
    text = (
        f"🌿 <b>{plant_id}. {name}</b>\n\n{body}\n\n"
        f"👥 {group_label}: {GROUP_NAME}\n📚 {source}"
    )
    parts = list(chunks(text))
    img = image_for(plant_id)
    if img:
        await bot.send_photo(
            chat_id,
            FSInputFile(img),
            caption=parts[0][:1024],
            parse_mode="HTML",
            reply_markup=plant_markup(lang),
        )
        for part in parts[1:]:
            await bot.send_message(chat_id, part, parse_mode="HTML")
    else:
        for part in parts:
            await bot.send_message(chat_id, part, parse_mode="HTML")
        await bot.send_message(chat_id, TEXT[lang]["not_found"], reply_markup=plant_markup(lang))


dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    row = conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        await message.answer(
            f"{TEXT['kk']['welcome']}\n\n{TEXT['kk']['hello']}\n\n"
            f"👥 Топ: {GROUP_NAME}\n\n{TEXT['kk']['choose_lang']}",
            reply_markup=language_menu(),
        )
    else:
        lang = row[0]
        await message.answer(TEXT[lang]["menu"], reply_markup=main_menu(lang))


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    if lang not in TEXT:
        await call.answer()
        return
    set_lang(call.from_user.id, lang)
    await call.answer()
    await edit_message(call.message, TEXT[lang]["menu"], main_menu(lang))


@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.answer()
    await edit_message(call.message, TEXT[lang]["menu"], main_menu(lang))


@dp.callback_query(F.data == "plants")
async def cb_plants(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.answer()
    await edit_message(
        call.message,
        f"🌱 {TEXT[lang]['plants']}\n\n{TEXT[lang]['choose_plant']}",
        category_menu(lang),
    )


@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    cat = call.data.split(":", 1)[1]
    if cat not in CATEGORIES:
        await call.answer()
        return
    await call.answer()
    await edit_message(
        call.message,
        f"{TEXT[lang][cat]}\n\n{TEXT[lang]['choose_plant']}",
        category_keyboard(cat, lang),
    )


@dp.callback_query(F.data.startswith("plant:"))
async def cb_plant(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    try:
        pid = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer()
        return
    if pid not in PLANT_BY_ID:
        await call.answer()
        return

    # Stop Telegram's button spinner immediately; translation can take time on first access.
    await call.answer(TEXT[lang]["translate_busy"])
    try:
        await send_plant(call.bot, call.from_user.id, pid, lang)
    except Exception as exc:
        print(f"Plant {pid} error: {exc}")
        await call.bot.send_message(call.from_user.id, "⚠️", reply_markup=plant_markup(lang))


@dp.callback_query(F.data == "search")
async def cb_search(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.answer()
    await edit_message(
        call.message,
        TEXT[lang]["search_help"],
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")]]
        ),
    )


@dp.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.answer()
    await edit_message(
        call.message,
        TEXT[lang]["about_text"],
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")]]
        ),
    )


@dp.callback_query(F.data == "language")
async def cb_language(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.answer()
    await edit_message(call.message, TEXT[lang]["choose_lang"], language_menu())


@dp.message(F.text)
async def search_message(message: Message):
    if not message.text or message.text.startswith("/"):
        return

    q = message.text.strip().casefold()
    if len(q) < 2:
        return

    lang = get_lang(message.from_user.id)
    # FAST SEARCH: use only local data, never call an online translator for all 115 records.
    # Also search Latin names appearing in the source text.
    results = []
    for p in PLANTS:
        hay = p["name_kk"].casefold()
        source = p.get("source_kk", "")
        if q in hay or q in source.casefold():
            results.append(p)
            continue

        # Support exact/partial numeric ID search.
        if q.isdigit() and int(q) == int(p["id"]):
            results.append(p)

    if not results:
        await message.answer(TEXT[lang]["not_found"], reply_markup=main_menu(lang))
        return

    rows = []
    for p in results[:30]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{p['id']}. {p['name_kk'][:48]}",
                    callback_data=f"plant:{p['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")])
    await message.answer("🔎 Нәтиже / Результат / Results:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def build_web_app():
    from aiohttp import web

    bot = Bot(BOT_TOKEN)
    app = web.Application()
    app["bot"] = bot

    async def health(_request):
        return web.Response(text="OK")

    async def telegram_webhook(request):
        try:
            data = await request.json()
            update = Update.model_validate(data, context={"bot": bot})
            await dp.feed_webhook_update(bot, update)
            return web.Response(text="OK")
        except Exception as exc:
            print(f"Webhook error: {exc}")
            # Telegram retries on non-2xx; keep handler resilient.
            return web.Response(status=500, text="Webhook error")

    async def on_startup(_app):
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        print(f"Telegram webhook set: {WEBHOOK_URL}")

    async def on_cleanup(_app):
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        finally:
            await bot.session.close()
            conn.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", telegram_webhook)
    return app


def main():
    from aiohttp import web

    app = asyncio.run(build_web_app())
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
