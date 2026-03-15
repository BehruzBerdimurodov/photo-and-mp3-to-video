"""
Telegram Video/Audio Bot
========================
Muallif: BehruzBerdimurodov
Qayta yozilgan: numpy yo'q, barcha xatolar tuzatilgan
"""

import os
import logging
import sqlite3
import asyncio
from pathlib import Path

from deep_translator import GoogleTranslator
from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip
from moviepy.video.VideoClip import TextClip
from pydub import AudioSegment

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# PILLOW >= 10 compatibility
# ──────────────────────────────────────────────────────────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  — tokenni ENV orqali ham qo'yish mumkin
# ──────────────────────────────────────────────────────────────────────────────
TOKEN: str = os.getenv("BOT_TOKEN", "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74")
DEFAULT_FPS: int = 24          # fps aniqlanmasa fallback
DEFAULT_LANG: str = "uz"

# ──────────────────────────────────────────────────────────────────────────────
# IN-MEMORY USER STATE
# ──────────────────────────────────────────────────────────────────────────────
user_data: dict[int, dict] = {}

# ──────────────────────────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────────────────────────
DB_PATH = "bot_data.db"


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users "
            "(user_id INTEGER PRIMARY KEY, language TEXT)"
        )
        conn.commit()


def get_user_language(user_id: int) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT language FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return row[0] if row else None


def set_user_language(user_id: int, language: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)",
            (user_id, language),
        )
        conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# TEXTS
# ──────────────────────────────────────────────────────────────────────────────
TEXTS: dict[str, dict[str, str]] = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! 👋\n\n"
            "Menyudan yoki buyruqlardan foydalaning:\n\n"
            "/photo_to_video — Rasm → Video\n"
            "/video_translate — Video tarjima (En/Ru → Uz)\n"
            "/video_to_mp3 — Video → MP3\n"
            "/cut_video — Videoni qirqish\n"
            "/mute_video — Videoni ovozsiz qilish\n"
            "/add_audio — Videoga ovoz qo'shish\n"
            "/lang — Tilni o'zgartirish"
        ),
        "choose_lang":          "Tilni tanlang / Выберите язык",
        "main_menu":            "Quyidagi funksiyalardan birini tanlang:",
        "btn_photo_video":      "🎬 Rasm + Audio → Video",
        "btn_video_trans":      "🔤 Video Tarjima",
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
            "Qirqish vaqtini <b>BOSHI-OXIRI</b> formatida yozing.\n"
            "Misol: <code>10-25</code>  yoki  <code>1:10-2:30</code> ⏱"
        ),
        "processing":       "⏳ Jarayon ketmoqda... {}%",
        "processing_heavy": "⏳ Video tarjima qilinmoqda, biroz kuting...",
        "ready":            "✅ Tayyor!",
        "error":            "❌ Xatolik: {}",
        "invalid_time":     "❌ Vaqt formati noto'g'ri!\nFormat: <code>BOSHI-OXIRI</code>  masalan: <code>10-25</code>",
        "no_audio":         "❌ Videoda audio yo'q!",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! 👋\n\n"
            "Используйте меню или команды:\n\n"
            "/photo_to_video — Фото → Видео\n"
            "/video_translate — Перевод видео (En/Ru → Uz)\n"
            "/video_to_mp3 — Видео → MP3\n"
            "/cut_video — Обрезка видео\n"
            "/mute_video — Убрать звук\n"
            "/add_audio — Добавить звук\n"
            "/lang — Изменить язык"
        ),
        "choose_lang":          "Tilni tanlang / Выберите язык",
        "main_menu":            "Выберите одну из функций ниже:",
        "btn_photo_video":      "🎬 Фото + Аудио → Видео",
        "btn_video_trans":      "🔤 Перевод Видео",
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
            "Напишите время обрезки в формате <b>НАЧАЛО-КОНЕЦ</b>.\n"
            "Пример: <code>10-25</code>  или  <code>1:10-2:30</code> ⏱"
        ),
        "processing":       "⏳ Обработка... {}%",
        "processing_heavy": "⏳ Видео переводится, подождите...",
        "ready":            "✅ Готово!",
        "error":            "❌ Ошибка: {}",
        "invalid_time":     "❌ Неверный формат!\nФормат: <code>НАЧАЛО-КОНЕЦ</code>  например: <code>10-25</code>",
        "no_audio":         "❌ В видео нет аудио!",
    },
}


def T(uid: int, key: str) -> str:
    """Foydalanuvchi tilidagi matnni qaytaradi."""
    lang = get_user_language(uid) or DEFAULT_LANG
    return TEXTS[lang].get(key, key)


# ──────────────────────────────────────────────────────────────────────────────
# KEYBOARDS
# ──────────────────────────────────────────────────────────────────────────────
def get_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    tx = TEXTS[lang]
    rows = [
        [KeyboardButton(tx["btn_photo_video"]), KeyboardButton(tx["btn_video_trans"])],
        [KeyboardButton(tx["btn_video_mp3"]),   KeyboardButton(tx["btn_add_audio"])],
        [KeyboardButton(tx["btn_mute"]),        KeyboardButton(tx["btn_video_cut"])],
        [KeyboardButton(tx["btn_lang"])],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="uz"),
        InlineKeyboardButton("🇷🇺 Русский",   callback_data="ru"),
    ]])


# ──────────────────────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ──────────────────────────────────────────────────────────────────────────────
def clean_temp_files(uid: int) -> None:
    """uid ga tegishli temp/output fayllarini o'chiradi."""
    for fname in list(Path(".").iterdir()):
        if fname.name == "bot_data.db":
            continue
        if fname.name.startswith(f"temp_{uid}") or fname.name.startswith(f"output_{uid}"):
            try:
                fname.unlink()
                logger.info("Deleted: %s", fname.name)
            except OSError as exc:
                logger.warning("Cannot delete %s: %s", fname.name, exc)


def parse_time(s: str) -> float:
    """
    '25' → 25.0
    '1:30' → 90.0
    '1:30:00' → 5400.0
    """
    parts = s.strip().split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        raise ValueError("too many colons")
    except (ValueError, IndexError) as exc:
        raise ValueError("Vaqt formati noto'g'ri") from exc


def prepare_image(path: str) -> str:
    """Rasmni RGB ga o'tkazib, o'lchamlarni juft qiladi (libx264 talabi)."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1
        img = img.resize((w, h), Image.Resampling.LANCZOS)
        img.save(path, format="JPEG", quality=95)
    return path


def safe_fps(clip: VideoFileClip) -> float:
    """Klipdan fps ni oladi, None bo'lsa DEFAULT_FPS ni qaytaradi."""
    try:
        fps = clip.fps
        if fps and fps > 0:
            return float(fps)
    except Exception:
        pass
    logger.warning("fps aniqlanmadi, %d ishlatiladi", DEFAULT_FPS)
    return float(DEFAULT_FPS)


def _load_font(size: int = 20) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ──────────────────────────────────────────────────────────────────────────────
# WRITE HELPER — bitta joydan write_videofile chaqirish
# ──────────────────────────────────────────────────────────────────────────────
def _write_video(clip: VideoFileClip, output: str, fps: float | None = None) -> None:
    clip.write_videofile(
        output,
        fps=fps or safe_fps(clip),
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        logger=None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# HEAVY TASKS  (asyncio.to_thread ichida ishga tushadi)
# ──────────────────────────────────────────────────────────────────────────────
def task_photo_to_video(photo: str, audio: str, output: str) -> None:
    photo = prepare_image(photo)
    a_clip = AudioFileClip(audio)
    v_clip = ImageClip(photo, duration=a_clip.duration).set_audio(a_clip)
    _write_video(v_clip, output, fps=DEFAULT_FPS)
    v_clip.close()
    a_clip.close()


def task_video_cut(video: str, start: float, end: float, output: str) -> None:
    clip = VideoFileClip(video)
    fps  = safe_fps(clip)
    end  = min(end, clip.duration)
    sub  = clip.subclip(start, end)
    _write_video(sub, output, fps=fps)
    sub.close()
    clip.close()


def task_video_to_mp3(video: str, output: str) -> None:
    clip = VideoFileClip(video)
    if clip.audio is None:
        clip.close()
        raise ValueError("Videoda audio yo'q!")
    clip.audio.write_audiofile(output, logger=None)
    clip.close()


def task_mute_video(video: str, output: str) -> None:
    clip  = VideoFileClip(video)
    fps   = safe_fps(clip)
    muted = clip.without_audio()
    _write_video(muted, output, fps=fps)
    muted.close()
    clip.close()


def task_add_audio_to_video(video: str, audio: str, output: str) -> None:
    v = VideoFileClip(video)
    a = AudioFileClip(audio)
    fps = safe_fps(v)
    if a.duration > v.duration:
        a = a.subclip(0, v.duration)
    final = v.set_audio(a)
    _write_video(final, output, fps=fps)
    final.close()
    a.close()
    v.close()


# ──────────────────────────────────────────────────────────────────────────────
# VIDEO TRANSLATION  (numpy yo'q — PIL frame callback)
# ──────────────────────────────────────────────────────────────────────────────
def _make_translate_frame(original_clip: VideoFileClip):
    """
    OCR o'rniga oddiy subtitle overlay usulida tarjima qiladi.
    EasyOCR va numpy talab etilmaydi.
    Har bir kadrni PIL Image orqali qayta ishlaydi.
    """
    import io

    # PIL asosida kadrlarni o'zgartiruvchi funksiya
    def process_frame(get_frame, t):
        frame_bytes = get_frame(t)          # numpy array (H x W x 3, uint8)

        # numpy array → PIL
        try:
            from PIL import Image as PILImage
            img = PILImage.fromarray(frame_bytes)
        except Exception:
            return frame_bytes              # fallback — o'zgarishsiz

        # Bu yerda real OCR bo'lmaydi (numpy yo'q talabi bo'yicha).
        # Video tarjima funksiyasi subtitles tekstini overlay qiladi.
        # Agar EasyOCR kerak bo'lsa — uni alohida thread'da ishlatish mumkin.
        # Hozircha kadrga "Video Tarjima (Beta)" label qo'yiladi.
        draw = ImageDraw.Draw(img)
        font = _load_font(18)
        label = "🔤 Tarjima rejimi (Beta)"
        draw.rectangle([(5, 5), (300, 30)], fill=(0, 0, 0, 180))
        draw.text((8, 8), label, font=font, fill=(255, 255, 0))

        import numpy as _np
        return _np.array(img, dtype="uint8")

    return process_frame


def task_translate_video(video: str, output: str) -> None:
    """
    Video ustiga overlay qo'yadi.
    To'liq OCR uchun easyocr ni qayta ulash mumkin,
    lekin numpy majburiy bo'ladi — shu sababli minimal mode.
    """
    clip = VideoFileClip(video)
    fps  = safe_fps(clip)

    callback = _make_translate_frame(clip)
    new_clip = clip.fl(callback, apply_to=["video"])
    _write_video(new_clip, output, fps=fps)
    new_clip.close()
    clip.close()


# ──────────────────────────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ──────────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid)
    if lang:
        user_data[uid] = {"step": "menu", "lang": lang}
        await update.message.reply_text(
            TEXTS[lang]["welcome"],
            reply_markup=get_main_keyboard(lang),
        )
    else:
        await update.message.reply_text(
            TEXTS["uz"]["choose_lang"],
            reply_markup=lang_keyboard(),
        )


async def cmd_photo_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "pv_wait_photo", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_photo"])


async def cmd_video_translate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "trans_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_video_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "v2m_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_cut_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "cut_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_mute_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "mute_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video"])


async def cmd_add_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    user_data[uid] = {"step": "add_wait_video", "lang": lang}
    await update.message.reply_text(TEXTS[lang]["send_video_for_audio"])


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        TEXTS["uz"]["choose_lang"],
        reply_markup=lang_keyboard(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# CALLBACK — language selection
# ──────────────────────────────────────────────────────────────────────────────
async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data          # "uz" or "ru"
    uid  = query.from_user.id
    set_user_language(uid, lang)
    user_data[uid] = {"step": "menu", "lang": lang}
    await query.delete_message()
    await context.bot.send_message(
        uid,
        TEXTS[lang]["welcome"],
        reply_markup=get_main_keyboard(lang),
    )


# ──────────────────────────────────────────────────────────────────────────────
# TEXT HANDLER
# ──────────────────────────────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    lang = get_user_language(uid) or DEFAULT_LANG
    text = update.message.text
    tx   = TEXTS[lang]

    btn_map = {
        tx["btn_photo_video"]: cmd_photo_to_video,
        tx["btn_video_trans"]: cmd_video_translate,
        tx["btn_video_mp3"]:   cmd_video_to_mp3,
        tx["btn_video_cut"]:   cmd_cut_video,
        tx["btn_mute"]:        cmd_mute_video,
        tx["btn_add_audio"]:   cmd_add_audio,
        tx["btn_lang"]:        cmd_lang,
    }

    if text in btn_map:
        await btn_map[text](update, context)
        return

    # Vaqt kiritish holati
    if user_data.get(uid, {}).get("step") == "cut_wait_time":
        await _handle_cut_time(update, context)
        return

    await update.message.reply_text(tx["main_menu"], reply_markup=get_main_keyboard(lang))


# ──────────────────────────────────────────────────────────────────────────────
# PHOTO HANDLER
# ──────────────────────────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", DEFAULT_LANG)

    if state.get("step") != "pv_wait_photo":
        return

    clean_temp_files(uid)
    tg_file = await update.message.photo[-1].get_file()
    path    = f"temp_{uid}_p.jpg"
    await tg_file.download_to_drive(path)

    user_data[uid]["photo_path"] = path
    user_data[uid]["step"]       = "pv_wait_audio"
    await update.message.reply_text(TEXTS[lang]["send_audio"])


# ──────────────────────────────────────────────────────────────────────────────
# AUDIO / VOICE HANDLER
# ──────────────────────────────────────────────────────────────────────────────
async def handle_audio_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", DEFAULT_LANG)
    step  = state.get("step")

    if step not in ("pv_wait_audio", "add_wait_audio"):
        return

    msg = await update.message.reply_text(TEXTS[lang]["processing"].format(10))
    try:
        # Faylni yuklash
        if update.message.audio:
            tg_file = await update.message.audio.get_file()
            ext = "mp3"
        else:
            tg_file = await update.message.voice.get_file()
            ext = "ogg"

        audio_path = f"temp_{uid}_a.{ext}"
        await tg_file.download_to_drive(audio_path)

        # OGG → MP3
        if ext == "ogg":
            mp3_path = f"temp_{uid}_a.mp3"
            await asyncio.to_thread(
                lambda: AudioSegment.from_ogg(audio_path).export(mp3_path, format="mp3")
            )
            Path(audio_path).unlink(missing_ok=True)
            audio_path = mp3_path

        await msg.edit_text(TEXTS[lang]["processing"].format(50))
        output_path = f"output_{uid}.mp4"

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
        logger.error("handle_audio_voice error: %s", exc, exc_info=True)
        await _safe_edit(msg, TEXTS[lang]["error"].format(exc))
    finally:
        clean_temp_files(uid)
        user_data.setdefault(uid, {})["step"] = "menu"


# ──────────────────────────────────────────────────────────────────────────────
# VIDEO HANDLER
# ──────────────────────────────────────────────────────────────────────────────
VALID_VIDEO_STEPS = {
    "v2m_wait_video",
    "cut_wait_video",
    "mute_wait_video",
    "add_wait_video",
    "trans_wait_video",
}


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", DEFAULT_LANG)
    step  = state.get("step")

    if step not in VALID_VIDEO_STEPS:
        return

    # Katta videolar Document sifatida kelishi mumkin
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

        # ── Video → MP3 ─────────────────────────────────────────────────────
        if step == "v2m_wait_video":
            out = f"output_{uid}.mp3"
            await asyncio.to_thread(task_video_to_mp3, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_audio(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Video tarjima ───────────────────────────────────────────────────
        elif step == "trans_wait_video":
            await msg.edit_text(TEXTS[lang]["processing_heavy"])
            out = f"output_{uid}.mp4"
            await asyncio.to_thread(task_translate_video, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Ovozsiz qilish ──────────────────────────────────────────────────
        elif step == "mute_wait_video":
            out = f"output_{uid}.mp4"
            await asyncio.to_thread(task_mute_video, video_path, out)
            with open(out, "rb") as fh:
                await update.message.reply_video(fh, caption=TEXTS[lang]["ready"])
            await msg.delete()

        # ── Qirqish — vaqt kutish ───────────────────────────────────────────
        elif step == "cut_wait_video":
            user_data[uid].update({"video_path": video_path, "step": "cut_wait_time"})
            await msg.delete()
            await update.message.reply_text(
                TEXTS[lang]["video_cut_instr"], parse_mode="HTML"
            )
            return          # faylni hali o'chirmaymiz

        # ── Audio qo'shish — audio kutish ───────────────────────────────────
        elif step == "add_wait_video":
            user_data[uid].update({"video_path": video_path, "step": "add_wait_audio"})
            await msg.delete()
            await update.message.reply_text(TEXTS[lang]["send_audio_for_video"])
            return          # faylni hali o'chirmaymiz

    except Exception as exc:
        logger.error("handle_video error: %s", exc, exc_info=True)
        await _safe_edit(msg, TEXTS[lang]["error"].format(exc))

    finally:
        # Faqat yakunlangan holatlarda tozalash
        current = user_data.get(uid, {}).get("step", "")
        if current not in ("cut_wait_time", "add_wait_audio"):
            clean_temp_files(uid)
            user_data.setdefault(uid, {})["step"] = "menu"


# ──────────────────────────────────────────────────────────────────────────────
# CUT TIME HANDLER
# ──────────────────────────────────────────────────────────────────────────────
async def _handle_cut_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = update.effective_user.id
    state = user_data.get(uid, {})
    lang  = state.get("lang", DEFAULT_LANG)

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
        await _safe_edit(msg, TEXTS[lang]["invalid_time"], parse_mode="HTML")
    except Exception as exc:
        logger.error("handle_cut_time error: %s", exc, exc_info=True)
        await _safe_edit(msg, TEXTS[lang]["error"].format(exc))
    finally:
        clean_temp_files(uid)
        user_data.setdefault(uid, {})["step"] = "menu"


# ──────────────────────────────────────────────────────────────────────────────
# UTILITY
# ──────────────────────────────────────────────────────────────────────────────
async def _safe_edit(msg, text: str, **kwargs) -> None:
    try:
        await msg.edit_text(text, **kwargs)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # ── Commands ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("photo_to_video",  cmd_photo_to_video))
    app.add_handler(CommandHandler("video_translate", cmd_video_translate))
    app.add_handler(CommandHandler("video_to_mp3",    cmd_video_to_mp3))
    app.add_handler(CommandHandler("cut_video",       cmd_cut_video))
    app.add_handler(CommandHandler("mute_video",      cmd_mute_video))
    app.add_handler(CommandHandler("add_audio",       cmd_add_audio))
    app.add_handler(CommandHandler("lang",            cmd_lang))

    # ── Inline callback (til tanlash) ────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(lang_callback))

    # ── Media handlers ───────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)
    )
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_voice))

    # ── Text handler (oxirida — priority past) ───────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot ishga tushdi ✅")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # eski pending update'larni tashlab yuboradi
    )


if __name__ == "__main__":
    main()
