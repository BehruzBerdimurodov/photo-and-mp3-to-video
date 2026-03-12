import os
import logging
import sqlite3
import asyncio
import numpy as np
import easyocr
from deep_translator import GoogleTranslator
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip
from pydub import AudioSegment
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  PILLOW COMPATIBILITY  (Pillow >= 10)
# ─────────────────────────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74"  # <-- o'z tokeningizni qo'ying

# ─────────────────────────────────────────────
#  EASYOCR — lazy init (import vaqtida emas,
#  birinchi ishlatilganda yuklanadi)
# ─────────────────────────────────────────────
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        logger.info("EasyOCR yuklanmoqda...")
        _ocr_reader = easyocr.Reader(["en", "ru"], gpu=False)
        logger.info("EasyOCR tayyor.")
    return _ocr_reader

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

def clean_temp_files(user_id: int):
    """Foydalanuvchiga tegishli vaqtinchalik fayllarni o'chirish."""
    try:
        for fname in os.listdir("."):
            if fname == "bot_data.db":
                continue
            if fname.startswith(f"temp_{user_id}") or fname.startswith(f"output_{user_id}"):
                try:
                    os.remove(fname)
                    logger.info(f"Deleted: {fname}")
                except OSError as exc:
                    logger.warning(f"Cannot delete {fname}: {exc}")
    except Exception as exc:
        logger.error(f"clean_temp_files error: {exc}")


def parse_time(time_str: str) -> float:
    """
    Vaqtni sekundga o'tkazish.
    Qabul qilinadigan formatlar: "25"  "1:30"  "1:30:00"
    """
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError
    except (ValueError, IndexError):
        raise ValueError("Vaqt formati noto'g'ri")


def prepare_image(image_path: str) -> str:
    """
    Rasmni video uchun tayyorlash:
    - RGB ga o'girish
    - o'lchamlarni juft qilish (libx264 talabi)
    """
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1
        img = img.resize((w, h), Image.Resampling.LANCZOS)
        img.save(image_path, format="JPEG", quality=95)
    return image_path


def _load_font(size: int = 20) -> ImageFont.FreeTypeFont:
    """Mavjud fontlardan birini yuklab beradi."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect("bot_data.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(user_id INTEGER PRIMARY KEY, language TEXT)"
    )
    conn.commit()
    conn.close()


def get_user_language(user_id: int):
    conn = sqlite3.connect("bot_data.db")
    row = conn.execute(
        "SELECT language FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def set_user_language(user_id: int, language: str):
    conn = sqlite3.connect("bot_data.db")
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)",
        (user_id, language),
    )
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
#  TEXTS
# ─────────────────────────────────────────────
TEXTS = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! 👋\n\n"
            "Menyudan yoki buyruqlardan foydalaning:\n\n"
            "/photo_to_video — Rasm → Video\n"
            "/video_translate — Video tarjima (Beta)\n"
            "/video_to_mp3 — Video → MP3\n"
            "/cut_video — Videoni qirqish\n"
            "/mute_video — Videoni ovozsiz qilish\n"
            "/add_audio — Videoga ovoz qo'shish\n"
            "/lang — Tilni o'zgartirish"
        ),
        "choose_lang":          "Tilni tanlang / Выберите язык",
        "main_menu":            "Quyidagi funksiyalardan birini tanlang:",
        "btn_photo_video":      "🎬 Rasm + Audio → Video",
        "btn_video_trans":      "🔤 Video Tarjima (En/Ru → Uz)",
        "btn_video_mp3":        "🎵 Video → MP3",
        "btn_video_cut":        "✂️ Videoni qirqish",
        "btn_mute":             "🔇 Videoni ovozsiz qilish",
        "btn_add_audio":        "🔉 Videoga ovoz qo'shish",
        "btn_lang":             "🌐 Tilni o'zgartirish",
        "send_photo":           "Iltimos, rasm yuboring 📸",
        "send_video":           "Iltimos, video yuboring 🎬",
        "send_audio":           "Endi audio yoki ovozli xabar yuboring 🎵",
        "send_video_for_audio": "Qaysi videoga ovoz qo'shmoqchisiz? Videoni yuboring 🎬",
        "send_audio_for_video": "Video qabul qilindi. Endi unga qo'yiladigan audioni yuboring 🎵",
        "video_cut_instr": (
            "Video qabul qilindi.\n"
            "Qirqish vaqtini <b>START-END</b> formatida yozing.\n"
            "Misol: <code>10-25</code>  yoki  <code>1:10-2:30</code> ⏱"
        ),
        "processing":       "⏳ Jarayon ketmoqda... {}%",
        "processing_heavy": "⏳ Video tarjima qilinmoqda. Bu biroz vaqt olishi mumkin...",
        "ready":            "✅ Tayyor!",
        "error":            "❌ Xatolik: {}",
        "invalid_time":     "❌ Vaqt formati noto'g'ri!\nFormat: <code>START-END</code>  masalan: <code>10-25</code>",
        "no_audio":         "❌ Videoda audio yo'q!",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! 👋\n\n"
            "Используйте меню или команды:\n\n"
            "/photo_to_video — Фото → Видео\n"
            "/video_translate — Перевод видео (Beta)\n"
            "/video_to_mp3 — Видео → MP3\n"
            "/cut_video — Обрезка видео\n"
            "/mute_video — Убрать звук\n"
            "/add_audio — Добавить звук\n"
            "/lang — Изменить язык"
        ),
        "choose_lang":          "Tilni tanlang / Выберите язык",
        "main_menu":            "Выберите одну из функций ниже:",
        "btn_photo_video":      "🎬 Фото + Аудио → Видео",
        "btn_video_trans":      "🔤 Перевод Видео (En/Ru → Uz)",
        "btn_video_mp3":        "🎵 Видео → MP3",
        "btn_video_cut":        "✂️ Обрезка видео",
        "btn_mute":             "🔇 Убрать звук из видео",
        "btn_add_audio":        "🔉 Добавить звук в видео",
        "btn_lang":             "🌐 Изменить язык",
        "send_photo":           "Пожалуйста, отправьте фото 📸",
        "send_video":           "Пожалуйста, отправьте видео 🎬",
        "send_audio":           "Теперь отправьте аудио или голосовое сообщение 🎵",
        "send_video_for_audio": "Отправьте видео, к которому нужно добавить звук 🎬",
        "send_audio_for_video": "Видео получено. Теперь отправьте аудио файл 🎵",
        "video_cut_instr": (
            "Видео получено.\n"
            "Напишите время обрезки в формате <b>START-END</b>.\n"
            "Пример: <code>10-25</code>  или  <code>1:10-2:30</code> ⏱"
        ),
        "processing":       "⏳ Обработка... {}%",
        "processing_heavy": "⏳ Видео переводится. Это может занять время...",
        "ready":            "✅ Готово!",
        "error":            "❌ Ошибка: {}",
        "invalid_time":     "❌ Неверный формат времени!\nФормат: <code>START-END</code>  например: <code>10-25</code>",
        "no_audio":         "❌ В видео нет аудио!",
    },
}

# In-memory user state
user_data: dict = {}

# ─────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────

def get_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    T = TEXTS[lang]
    kb = [
        [KeyboardButton(T["btn_photo_video"]),  KeyboardButton(T["btn_video_trans"])],
        [KeyboardButton(T["btn_video_mp3"]),    KeyboardButton(T["btn_add_audio"])],
        [KeyboardButton(T["btn_mute"]),         KeyboardButton(T["btn_video_cut"])],
        [KeyboardButton(T["btn_lang"])],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ─────────────────────────────────────────────
#  HEAVY TASKS  (run in thread via asyncio.to_thread)
# ─────────────────────────────────────────────

def task_photo_to_video(photo_path: str, audio_path: str, output_path: str):
    photo = prepare_image(photo_path)
    audio = AudioFileClip(audio_path)
    video = ImageClip(photo, duration=audio.duration).set_audio(audio)
    video.write_videofile(
        output_path, fps=24,
        codec="libx264", audio_codec="aac",
        preset="fast", logger=None,
    )
    video.close()
    audio.close()


def task_video_cut(video_path: str, start: float, end: float, output_path: str):
    clip = VideoFileClip(video_path)
    end  = min(end, clip.duration)
    sub  = clip.subclip(start, end)
    sub.write_videofile(
        output_path,
        codec="libx264", audio_codec="aac",
        preset="fast", logger=None,
    )
    sub.close()
    clip.close()


def task_video_to_mp3(video_path: str, audio_output: str):
    clip = VideoFileClip(video_path)
    if clip.audio is None:
        clip.close()
        raise ValueError("Videoda audio yo'q!")
    clip.audio.write_audiofile(audio_output, logger=None)
    clip.close()


def task_mute_video(video_path: str, output_path: str):
    clip  = VideoFileClip(video_path)
    muted = clip.without_audio()
    muted.write_videofile(
        output_path,
        codec="libx264", audio_codec="aac",
        preset="fast", logger=None,
    )
    muted.close()
    clip.close()


def task_add_audio_to_video(video_path: str, audio_path: str, output_path: str):
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    if audio.duration > video.duration:
        audio = audio.subclip(0, video.duration)
    final = video.set_audio(audio)
    final.write_videofile(
        output_path,
        codec="libx264", audio_codec="aac",
        preset="fast", logger=None,
    )
    final.close()
    audio.close()
    video.close()

# ─────────────────────────────────────────────
#  VIDEO TRANSLATION
# ─────────────────────────────────────────────

def _translate_frame(get_frame, t):
    """
    MoviePy fl() uchun kadr callback.
    Har bir kadrga OCR + tarjima + matn yozish.
    """
    frame: np.ndarray = get_frame(t)

    try:
        ocr_results = get_ocr_reader().readtext(frame)
    except Exception as exc:
        logger.warning(f"OCR error at t={t:.2f}: {exc}")
        return frame

    if not ocr_results:
        return frame

    # numpy → PIL (uint8 majburiy)
    img  = Image.fromarray(frame.astype("uint8"))
    draw = ImageDraw.Draw(img)
    font = _load_font(20)

    for (bbox, text, prob) in ocr_results:
        if prob < 0.4 or not text.strip():
            continue

        # Tarjima
        try:
            translated = GoogleTranslator(source="auto", target="uz").translate(text)
            if not translated:
                translated = text
        except Exception as exc:
            logger.warning(f"Translation error: {exc}")
            translated = text

        # Koordinatalar
        tl = (int(bbox[0][0]), int(bbox[0][1]))
        br = (int(bbox[2][0]), int(bbox[2][1]))

        # Orqa fon (qora) + oq matn
        draw.rectangle([tl, br], fill=(0, 0, 0))
        draw.text(tl, translated, font=font, fill=(255, 255, 255))

    # PIL → numpy uint8 (MoviePy talabi)
    return np.array(img, dtype="uint8")


def task_translate_video(video_path: str, output_path: str):
    clip     = VideoFileClip(video_path)
    # apply_to=["video"] — faqat video kanalga, audioga tegmaydi
    new_clip = clip.fl(_translate_frame, apply_to=["video"])
    new_clip.write_videofile(
        output_path,
        codec="libx264", audio_codec="aac",
        preset="ultrafast", logger=None,
    )
    new_clip.close()
    clip.close()

# ─────────────────────────────────────────────
#  COMMAND HANDLERS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid)
    if lang:
        user_data[uid] = {"step": "menu", "lang": lang}
        await update.message.reply_text(
            TEXTS[lang]["welcome"],
            reply_markup=get_main_keyboard(lang),
        )
    else:
        kb = [[
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="uz"),
            InlineKeyboardButton("🇷🇺 Русский",   callback_data="ru"),
        ]]
        await update.message.reply_text(
            TEXTS["uz"]["choose_lang"],
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def cmd_photo_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "pv_wait_photo", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_photo"])


async def cmd_video_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "trans_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_video_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "v2m_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_cut_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "cut_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_mute_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "mute_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_add_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    user_data[uid] = {"step": "add_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video_for_audio"])


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="uz"),
        InlineKeyboardButton("🇷🇺 Русский",   callback_data="ru"),
    ]]
    await update.message.reply_text(
        TEXTS["uz"]["choose_lang"],
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ─────────────────────────────────────────────
#  CALLBACK — til tanlash
# ─────────────────────────────────────────────

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data           # "uz" yoki "ru"
    uid  = query.from_user.id
    set_user_language(uid, lang)
    user_data[uid] = {"step": "menu", "lang": lang}
    await query.delete_message()
    await context.bot.send_message(
        uid,
        TEXTS[lang]["welcome"],
        reply_markup=get_main_keyboard(lang),
    )

# ─────────────────────────────────────────────
#  TEXT HANDLER  (reply tugmalar + vaqt kiritish)
# ─────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    lang = get_user_language(uid) or "uz"
    text = update.message.text
    T    = TEXTS[lang]

    btn_map = {
        T["btn_photo_video"]: cmd_photo_to_video,
        T["btn_video_trans"]: cmd_video_translate,
        T["btn_video_mp3"]:   cmd_video_to_mp3,
        T["btn_video_cut"]:   cmd_cut_video,
        T["btn_mute"]:        cmd_mute_video,
        T["btn_add_audio"]:   cmd_add_audio,
        T["btn_lang"]:        cmd_lang,
    }
    if text in btn_map:
        await btn_map[text](update, context)
        return

    # Vaqt kiritish holati
    if user_data.get(uid, {}).get("step") == "cut_wait_time":
        await handle_cut_time(update, context)
        return

    await update.message.reply_text(T["main_menu"], reply_markup=get_main_keyboard(lang))

# ─────────────────────────────────────────────
#  PHOTO HANDLER
# ─────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", "uz")

    if state.get("step") != "pv_wait_photo":
        return

    clean_temp_files(uid)
    f    = await update.message.photo[-1].get_file()
    path = f"temp_{uid}_p.jpg"
    await f.download_to_drive(path)

    user_data[uid]["photo_path"] = path
    user_data[uid]["step"]       = "pv_wait_audio"
    await update.message.reply_text(TEXTS[lang]["send_audio"])

# ─────────────────────────────────────────────
#  AUDIO / VOICE HANDLER
# ─────────────────────────────────────────────

async def handle_audio_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", "uz")
    step  = state.get("step")

    if step not in ("pv_wait_audio", "add_wait_audio"):
        return

    msg = await update.message.reply_text(TEXTS[lang]["processing"].format(10))
    try:
        # Fayl yuklash
        if update.message.audio:
            tg_file = await update.message.audio.get_file()
            ext     = "mp3"
        else:
            tg_file = await update.message.voice.get_file()
            ext     = "ogg"

        audio_path = f"temp_{uid}_a.{ext}"
        await tg_file.download_to_drive(audio_path)

        # OGG → MP3
        if ext == "ogg":
            mp3_path = f"temp_{uid}_a.mp3"
            await asyncio.to_thread(
                lambda: AudioSegment.from_ogg(audio_path).export(mp3_path, format="mp3")
            )
            os.remove(audio_path)
            audio_path = mp3_path

        output_path = f"output_{uid}.mp4"
        await msg.edit_text(TEXTS[lang]["processing"].format(50))

        if step == "pv_wait_audio":
            await asyncio.to_thread(
                task_photo_to_video, state["photo_path"], audio_path, output_path
            )
        else:  # add_wait_audio
            await asyncio.to_thread(
                task_add_audio_to_video, state["video_path"], audio_path, output_path
            )

        await msg.edit_text(TEXTS[lang]["processing"].format(100))
        with open(output_path, "rb") as fh:
            await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
        await msg.delete()

    except Exception as exc:
        logger.error(f"handle_audio_voice error: {exc}", exc_info=True)
        try:
            await msg.edit_text(TEXTS[lang]["error"].format(str(exc)))
        except Exception:
            pass
    finally:
        clean_temp_files(uid)
        user_data.setdefault(uid, {})["step"] = "menu"

# ─────────────────────────────────────────────
#  VIDEO HANDLER
# ─────────────────────────────────────────────

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", "uz")
    step  = state.get("step")

    valid = {"v2m_wait_video", "cut_wait_video", "mute_wait_video",
             "add_wait_video", "trans_wait_video"}
    if step not in valid:
        return

    # Telegram ba'zan katta videolarni Document sifatida yuboradi
    video_obj = update.message.video or update.message.document
    if video_obj is None:
        await update.message.reply_text(TEXTS[lang]["send_video"])
        return

    clean_temp_files(uid)
    msg = await update.message.reply_text(TEXTS[lang]["processing"].format(5))

    try:
        tg_file    = await video_obj.get_file()
        video_path = f"temp_{uid}_v.mp4"
        await tg_file.download_to_drive(video_path)
        await msg.edit_text(TEXTS[lang]["processing"].format(20))

        # ── Video → MP3 ──────────────────────────────────────
        if step == "v2m_wait_video":
            out = f"output_{uid}.mp3"
            await asyncio.to_thread(task_video_to_mp3, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_audio(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Video tarjima ─────────────────────────────────────
        elif step == "trans_wait_video":
            await msg.edit_text(TEXTS[lang]["processing_heavy"])
            out = f"output_{uid}.mp4"
            await asyncio.to_thread(task_translate_video, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Ovozsiz qilish ───────────────────────────────────
        elif step == "mute_wait_video":
            out = f"output_{uid}.mp4"
            await asyncio.to_thread(task_mute_video, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Qirqish (vaqt kutish) — keyingi state ─────────────
        elif step == "cut_wait_video":
            user_data[uid].update({"video_path": video_path, "step": "cut_wait_time"})
            await msg.delete()
            await update.message.reply_text(
                TEXTS[lang]["video_cut_instr"], parse_mode="HTML"
            )
            return  # clean_temp_files chaqirilmaydi

        # ── Audio qo'shish (audio kutish) — keyingi state ─────
        elif step == "add_wait_video":
            user_data[uid].update({"video_path": video_path, "step": "add_wait_audio"})
            await msg.delete()
            await update.message.reply_text(TEXTS[lang]["send_audio_for_video"])
            return  # clean_temp_files chaqirilmaydi

    except Exception as exc:
        logger.error(f"handle_video error: {exc}", exc_info=True)
        try:
            await msg.edit_text(TEXTS[lang]["error"].format(str(exc)))
        except Exception:
            pass
    finally:
        # Faqat yakunlangan holatlarda tozalash (cut/add emas)
        current_step = user_data.get(uid, {}).get("step", "")
        if current_step not in ("cut_wait_time", "add_wait_audio"):
            clean_temp_files(uid)
            user_data.setdefault(uid, {})["step"] = "menu"

# ─────────────────────────────────────────────
#  CUT TIME HANDLER
# ─────────────────────────────────────────────

async def handle_cut_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", "uz")

    if not state.get("video_path"):
        return

    msg = await update.message.reply_text(TEXTS[lang]["processing"].format(20))
    try:
        raw = update.message.text.strip()

        if "-" not in raw:
            await msg.edit_text(TEXTS[lang]["invalid_time"], parse_mode="HTML")
            return

        left, right = raw.split("-", 1)
        start_t = parse_time(left)
        end_t   = parse_time(right)

        if start_t < 0 or end_t <= start_t:
            await msg.edit_text(TEXTS[lang]["invalid_time"], parse_mode="HTML")
            return

        output_path = f"output_{uid}.mp4"
        await asyncio.to_thread(
            task_video_cut, state["video_path"], start_t, end_t, output_path
        )
        with open(output_path, "rb") as fh:
            await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
        await msg.delete()

    except ValueError:
        await msg.edit_text(TEXTS[lang]["invalid_time"], parse_mode="HTML")
    except Exception as exc:
        logger.error(f"handle_cut_time error: {exc}", exc_info=True)
        try:
            await msg.edit_text(TEXTS[lang]["error"].format(str(exc)))
        except Exception:
            pass
    finally:
        clean_temp_files(uid)
        user_data.setdefault(uid, {})["step"] = "menu"

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("photo_to_video",  cmd_photo_to_video))
    app.add_handler(CommandHandler("video_translate", cmd_video_translate))
    app.add_handler(CommandHandler("video_to_mp3",    cmd_video_to_mp3))
    app.add_handler(CommandHandler("cut_video",       cmd_cut_video))
    app.add_handler(CommandHandler("mute_video",      cmd_mute_video))
    app.add_handler(CommandHandler("add_audio",       cmd_add_audio))
    app.add_handler(CommandHandler("lang",            cmd_lang))

    # Inline tugmalar (til tanlash)
    app.add_handler(CallbackQueryHandler(lang_callback))

    # Text (reply tugmalar + vaqt kiritish)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Media
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)
    )
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_voice))

    logger.info("Bot ishga tushdi ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
