import asyncio
import json
import os
import sqlite3
from pathlib import Path
from contextlib import suppress

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AUTHOR = os.getenv("BOT_AUTHOR", "ХБ-31").strip()
PORT = int(os.getenv("PORT", "10000"))

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "plants_kk.json"
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
        "search_help": "🔎 Өсімдіктің қазақша немесе латынша атауын жазыңыз:\nМысалы: Қарағайлы шырша",
        "not_found": "Өсімдік табылмады.",
        "about_text": "Бұл бот берілген оқу материалдары негізінде 115 өсімдік туралы ақпаратты қарауға арналған.\n\nАвтор: ХБ-31",
        "source": "Дереккөз: берілген оқу материалдары.",
        "no_text": "Бұл түр бойынша бастапқы материалда толық сипаттама мәтіні берілмеген.",
    },
    "ru": {
        "choose_lang": "🌐 Выберите язык:",
        "welcome": "🌿 Энциклопедия растений",
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
        "search_help": "🔎 Введите казахское название или латинское название растения:\nНапример: Қарағайлы шырша",
        "not_found": "Растение не найдено.",
        "about_text": "Этот бот предназначен для просмотра информации о 115 растениях на основе предоставленных учебных материалов.\n\nАвтор: ХБ-31",
        "source": "Источник: предоставленные учебные материалы.",
        "no_text": "В исходном материале нет полного текстового описания этого вида.",
    },
    "en": {
        "choose_lang": "🌐 Choose a language:",
        "welcome": "🌿 Plant Encyclopedia",
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
        "search_help": "🔎 Enter the Kazakh or Latin name of the plant:\nExample: Қарағайлы шырша",
        "not_found": "Plant not found.",
        "about_text": "This bot is designed to browse information about 115 plants based on the provided educational materials.\n\nAuthor: ХБ-31",
        "source": "Source: provided educational materials.",
        "no_text": "The supplied source material does not contain a full textual description for this species.",
    },
}

conn = sqlite3.connect(DB_FILE)
conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT NOT NULL)")
conn.execute("""CREATE TABLE IF NOT EXISTS translations (
    plant_id INTEGER,
    lang TEXT,
    name TEXT,
    body TEXT,
    PRIMARY KEY (plant_id, lang)
)""")
conn.commit()


def get_lang(user_id: int) -> str:
    row = conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else "kk"


def set_lang(user_id: int, lang: str) -> None:
    conn.execute(
        "INSERT INTO users(user_id,lang) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
        (user_id, lang),
    )
    conn.commit()


def translate(text: str, target: str) -> str:
    if not text or target == "kk" or GoogleTranslator is None:
        return text
    pieces = []
    current = ""
    for para in text.split("\n\n"):
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) > 3000 and current:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    out = []
    for piece in pieces:
        try:
            out.append(GoogleTranslator(source="kk", target=target).translate(piece))
        except Exception:
            out.append(piece)
    return "\n\n".join(out)


def translated(plant: dict, lang: str):
    if lang == "kk":
        return plant["name_kk"], plant["source_kk"]
    row = conn.execute(
        "SELECT name,body FROM translations WHERE plant_id=? AND lang=?",
        (plant["id"], lang),
    ).fetchone()
    if row:
        return row
    name = translate(plant["name_kk"], lang)
    body = translate(plant["source_kk"], lang)
    conn.execute(
        "INSERT OR REPLACE INTO translations(plant_id,lang,name,body) VALUES(?,?,?,?)",
        (plant["id"], lang, name, body),
    )
    conn.commit()
    return name, body


def image_for(plant_id: int):
    stem = f"plant_{plant_id:03d}"
    matches = list(IMAGE_DIR.glob(stem + ".*"))
    return matches[0] if matches else None


def language_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang:kk")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
    ])


def main_menu(lang: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXT[lang]["plants"], callback_data="plants")],
        [InlineKeyboardButton(text=TEXT[lang]["search"], callback_data="search")],
        [InlineKeyboardButton(text=TEXT[lang]["about"], callback_data="about")],
        [InlineKeyboardButton(text=TEXT[lang]["language"], callback_data="language")],
    ])


def category_menu(lang: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXT[lang]["trees"], callback_data="cat:trees")],
        [InlineKeyboardButton(text=TEXT[lang]["flowers"], callback_data="cat:flowers")],
        [InlineKeyboardButton(text=TEXT[lang]["field"], callback_data="cat:field")],
        [InlineKeyboardButton(text=TEXT[lang]["lower"], callback_data="cat:lower")],
        [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")],
    ])


def category_keyboard(category: str, lang: str):
    ids = list(CATEGORIES[category])
    rows = []
    for pid in ids:
        p = PLANT_BY_ID[pid]
        name, _ = translated(p, lang)
        rows.append([InlineKeyboardButton(text=name[:50], callback_data=f"plant:{pid}")])
    rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="plants")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plant_text(plant_id: int, lang: str):
    plant = PLANT_BY_ID[plant_id]
    name, body = translated(plant, lang)
    if not body.strip():
        body = TEXT[lang]["no_text"]
    return f"🌿 <b>{plant_id}. {name}</b>\n\n{body}\n\n👤 {TEXT[lang]['about'].split()[1] if lang=='kk' else ('Автор' if lang=='ru' else 'Author')}: {AUTHOR}\n📚 {TEXT[lang]['source']}"


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
    text = plant_text(plant_id, lang)
    parts = list(chunks(text))
    img = image_for(plant_id)
    if img:
        with img.open("rb") as f:
            await bot.send_photo(chat_id, f, caption=parts[0][:1024], parse_mode="HTML")
        for part in parts[1:]:
            await bot.send_message(chat_id, part, parse_mode="HTML")
    else:
        for part in parts:
            await bot.send_message(chat_id, part, parse_mode="HTML")
    await bot.send_message(
        chat_id,
        TEXT[lang]["menu_back"],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["plants"], callback_data="plants")],
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")],
        ]),
    )


dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    row = conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        await message.answer(
            f"{TEXT['kk']['welcome']}\n\nСәлем! Ботқа қош келдіңіз.\nАвтор: {AUTHOR}\n\n{TEXT['kk']['choose_lang']}",
            reply_markup=language_menu(),
        )
    else:
        lang = row[0]
        await message.answer(TEXT[lang]["menu"], reply_markup=main_menu(lang))


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    set_lang(call.from_user.id, lang)
    await call.message.edit_text(TEXT[lang]["menu"], reply_markup=main_menu(lang))
    await call.answer()


@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(TEXT[lang]["menu"], reply_markup=main_menu(lang))
    await call.answer()


@dp.callback_query(F.data == "plants")
async def cb_plants(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(f"🌱 {TEXT[lang]['plants']}\n\n{TEXT[lang]['menu'].split('\\n\\n',1)[-1]}", reply_markup=category_menu(lang))
    await call.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    cat = call.data.split(":", 1)[1]
    if cat not in CATEGORIES:
        await call.answer()
        return
    await call.message.edit_text(f"{TEXT[lang][cat]}\n\nӨсімдікті таңдаңыз:" if lang == "kk" else f"{TEXT[lang][cat]}\n\n{('Выберите растение:' if lang=='ru' else 'Choose a plant:')}", reply_markup=category_keyboard(cat, lang))
    await call.answer()


@dp.callback_query(F.data.startswith("plant:"))
async def cb_plant(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    pid = int(call.data.split(":", 1)[1])
    if pid in PLANT_BY_ID:
        await send_plant(call.bot, call.from_user.id, pid, lang)
    await call.answer()


@dp.callback_query(F.data == "search")
async def cb_search(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(
        TEXT[lang]["search_help"],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")]
        ]),
    )
    await call.answer()


@dp.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(
        TEXT[lang]["about_text"],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")]
        ]),
    )
    await call.answer()


@dp.callback_query(F.data == "language")
async def cb_language(call: CallbackQuery):
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(TEXT[lang]["choose_lang"], reply_markup=language_menu())
    await call.answer()


@dp.message(F.text)
async def search_message(message: Message):
    if not message.text or message.text.startswith("/"):
        return
    lang = get_lang(message.from_user.id)
    q = message.text.strip().casefold()
    if len(q) < 2:
        await message.answer(TEXT[lang]["not_found"])
        return
    results = []
    for p in PLANTS:
        name = p["name_kk"]
        hay = [name.casefold()]
        if lang != "kk":
            translated_name, _ = translated(p, lang)
            hay.append(translated_name.casefold())
        if any(q in s for s in hay):
            results.append(p)
    if not results:
        await message.answer(TEXT[lang]["not_found"], reply_markup=main_menu(lang))
        return
    rows = []
    for p in results[:30]:
        pname, _ = translated(p, lang)
        rows.append([InlineKeyboardButton(text=f"{p['id']}. {pname[:48]}", callback_data=f"plant:{p['id']}")])
    rows.append([InlineKeyboardButton(text=TEXT[lang]["back"], callback_data="menu")])
    await message.answer("🔎", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def health_server():
    from aiohttp import web
    app = web.Application()

    async def health(_request):
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def main():
    bot = Bot(BOT_TOKEN)
    try:
        await asyncio.gather(dp.start_polling(bot), health_server())
    finally:
        await bot.session.close()
        conn.close()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
