import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip
from pydub import AudioSegment

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ma'lumotlar bazasi yaratish
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, language TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  photo_path TEXT,
                  audio_path TEXT,
                  video_path TEXT,
                  cut_video_path TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Til matnlari
TEXTS = {
    'uz': {
        'welcome': "Assalomu alaykum! 👋\n\nIltimos, tilni tanlang:",
        'choose_lang': "Tilni tanlang:",
        'lang_selected': "✅ Til tanlandi: O'zbekcha\n\nQuyidagi funksiyalardan birini tanlang:",
        'main_menu': "Quyidagi funksiyalardan birini tanlang:",
        'photo_to_video': "🎬 Rasm + Audio → Video",
        'video_to_mp3': "🎵 Video → MP3",
        'cut_video': "✂️ Videoni kesish",
        'change_language': "🌐 Tilni o'zgartirish",
        'back_to_menu': "🔙 Asosiy menyu",
        'send_photo': "Iltimos, rasm yuboring 📸",
        'photo_received': "Rasm qabul qilindi! Endi audio yuboring 🎵",
        'send_video': "Iltimos, video yuboring 🎬",
        'video_received': "Video qabul qilindi! ⏳",
        'cut_send_range': "Qaysi qismini kesamiz?\nMasalan: 00:10-00:45",
        'invalid_range': "❌ Format noto‘g‘ri! Masalan shunday kiriting: 00:10-01:00",
        'cut_ready': "✂️ Tayyor! Kesilgan video quyida:",
        'processing': "⏳ Jarayon: {}%",
        'complete': "100% – Tayyor!",
        'video_ready': "Video tayyor! 🎬",
        'audio_ready': "MP3 tayyor! 🎵",
        'send_again': "\nYana ishlash uchun pastdagi tugmalardan foydalaning 🔄",
        'start_first': "Iltimos /start bosing!",
        'error': "Xatolik: {}"
    },
    'ru': {
        'welcome': "Здравствуйте! 👋\n\nПожалуйста, выберите язык:",
        'choose_lang': "Выберите язык:",
        'lang_selected': "✅ Язык выбран: Русский\n\nВыберите функцию:",
        'main_menu': "Выберите функцию:",
        'photo_to_video': "🎬 Фото + Аудио → Видео",
        'video_to_mp3': "🎵 Видео → MP3",
        'cut_video': "✂️ Вырезать часть видео",
        'change_language': "🌐 Изменить язык",
        'send_photo': "Отправьте фото 📸",
        'photo_received': "Фото получено! Теперь аудио 🎵",
        'send_video': "Отправьте видео 🎬",
        'video_received': "Видео получено! ⏳",
        'cut_send_range': "Какой фрагмент вырезать?\nНапример: 00:10-00:45",
        'invalid_range': "❌ Неверный формат! Введите так: 00:10-01:00",
        'cut_ready': "✂️ Готово! Вырезанное видео:",
        'processing': "⏳ Процесс: {}%",
        'complete': "100% – Готово!",
        'video_ready': "Видео готово! 🎬",
        'audio_ready': "MP3 готов! 🎵",
        'send_again': "\nДля продолжения используйте кнопки 🔄",
        'start_first': "Нажмите /start!",
        'error': "Ошибка: {}"
    }
}

# Foydalanuvchi maʼlumotlari saqlanadi
user_data = {}

def get_main_keyboard(lang):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['photo_to_video'])],
        [KeyboardButton(TEXTS[lang]['video_to_mp3'])],
        [KeyboardButton(TEXTS[lang]['cut_video'])],
        [KeyboardButton(TEXTS[lang]['change_language'])]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # Foydalanuvchi bazada yo'q bo'lsa til tanlash oynasi beriladi
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()

    if result:
        lang = result[0]
        await update.message.reply_text(TEXTS[lang]['main_menu'],
                                        reply_markup=get_main_keyboard(lang))
    else:
        keyboard = [
            [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz')],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')]
        ]
        await update.message.reply_text(TEXTS['uz']['choose_lang'],
                                        reply_markup=InlineKeyboardMarkup(keyboard))


# Til tanlash tugmasi
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]

        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (user_id, language) VALUES (?,?)",
                  (user_id, lang))
        conn.commit()
        conn.close()

        await query.edit_message_text(TEXTS[lang]['lang_selected'],
                                      reply_markup=get_main_keyboard(lang))


# Matnli tugmalar
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    lang = get_user_lang(user_id)
    text = update.message.text

    if text == TEXTS[lang]['photo_to_video']:
        user_data[user_id] = {'step': 'waiting_photo', 'lang': lang}
        await update.message.reply_text(TEXTS[lang]['send_photo'])

    elif text == TEXTS[lang]['video_to_mp3']:
        user_data[user_id] = {'step': 'waiting_video_mp3', 'lang': lang}
        await update.message.reply_text(TEXTS[lang]['send_video'])

    elif text == TEXTS[lang]['cut_video']:
        user_data[user_id] = {'step': 'waiting_cut_video', 'lang': lang}
        await update.message.reply_text(TEXTS[lang]['send_video'])

    elif text == TEXTS[lang]['change_language']:
        keyboard = [
            [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz')],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')]
        ]
        await update.message.reply_text(TEXTS[lang]['choose_lang'],
                                        reply_markup=InlineKeyboardMarkup(keyboard))

    else:
        await update.message.reply_text(TEXTS[lang]['main_menu'],
                                        reply_markup=get_main_keyboard(lang))


# Foydalanuvchi tili
def get_user_lang(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 'uz'



# VIDEO → MP3
async def handle_video_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, lang):
    video = await update.message.video.get_file()
    video_path = f"{user_id}_video.mp4"
    await video.download_to_drive(video_path)

    audio_path = f"{user_id}_audio.mp3"

    clip = VideoFileClip(video_path)
    clip.audio.write_audiofile(audio_path)
    clip.close()

    await update.message.reply_audio(audio=open(audio_path, "rb"))
    await update.message.reply_text(TEXTS[lang]['audio_ready'] + TEXTS[lang]['send_again'],
                                    reply_markup=get_main_keyboard(lang))

    os.remove(video_path)
    os.remove(audio_path)



# ✂️ VIDEO CUT
async def handle_video_cut(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, lang):
    video = await update.message.video.get_file()
    video_path = f"{user_id}_cut_input.mp4"
    await video.download_to_drive(video_path)

    user_data[user_id]['step'] = 'waiting_cut_range'
    user_data[user_id]['video_path'] = video_path

    await update.message.reply_text(TEXTS[lang]['cut_send_range'])



# Range qabul qilish
async def handle_cut_range(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, lang):
    text = update.message.text.strip()

    # Format tekshirish (00:12-01:30)
    if "-" not in text:
        await update.message.reply_text(TEXTS[lang]['invalid_range'])
        return

    start, end = text.split("-")

    def to_seconds(t):
        try:
            m, s = t.split(":")
            return int(m) * 60 + int(s)
        except:
            return None

    start_s = to_seconds(start)
    end_s = to_seconds(end)

    if start_s is None or end_s is None or end_s <= start_s:
        await update.message.reply_text(TEXTS[lang]['invalid_range'])
        return

    video_path = user_data[user_id]['video_path']
    out_path = f"{user_id}_cut_output.mp4"

    # Kesish
    clip = VideoFileClip(video_path)
    cut = clip.subclip(start_s, end_s)
    cut.write_videofile(out_path)
    clip.close()

    await update.message.reply_text(TEXTS[lang]['cut_ready'])
    await update.message.reply_video(video=open(out_path, "rb"),
                                     reply_markup=get_main_keyboard(lang))

    os.remove(video_path)
    os.remove(out_path)
    user_data[user_id] = {}



# Rasm + Audio → Video
async def handle_photo_and_audio(update, context, user_id, lang):
    if update.message.photo:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_path = f"{user_id}_photo.jpg"
        await photo_file.download_to_drive(photo_path)
        user_data[user_id]['photo_path'] = photo_path
        user_data[user_id]['step'] = 'waiting_audio'
        await update.message.reply_text(TEXTS[lang]['photo_received'])

    elif update.message.audio or update.message.voice:
        audio = update.message.audio or update.message.voice
        audio_file = await audio.get_file()
        audio_path = f"{user_id}_audio.ogg"
        await audio_file.download_to_drive(audio_path)
        user_data[user_id]['audio_path'] = audio_path

        # Create video
        out_path = f"{user_id}_output.mp4"
        image_clip = ImageClip(user_data[user_id]['photo_path']).set_duration(5)
        audio_clip = AudioFileClip(audio_path)
        final_video = image_clip.set_audio(audio_clip)
        final_video.write_videofile(out_path)
        image_clip.close()
        audio_clip.close()

        await update.message.reply_video(video=open(out_path, "rb"),
                                         reply_markup=get_main_keyboard(lang))

        os.remove(user_data[user_id]['photo_path'])
        os.remove(audio_path)
        os.remove(out_path)
        user_data[user_id] = {}



# Media handler
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    lang = get_user_lang(user_id)

    if user_id not in user_data:
        await update.message.reply_text(TEXTS[lang]['start_first'])
        return

    step = user_data[user_id].get('step')

    if step == 'waiting_video_mp3':
        await handle_video_to_mp3(update, context, user_id, lang)

    elif step == 'waiting_cut_video':
        await handle_video_cut(update, context, user_id, lang)

    elif step == 'waiting_cut_range':
        await handle_cut_range(update, context, user_id, lang)

    elif step in ['waiting_photo', 'waiting_audio']:
        await handle_photo_and_audio(update, context, user_id, lang)



# Botni ishga tushirish
def main():
    init_db()
    TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74"

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO | filters.AUDIO | filters.VOICE,
                                   handle_media))

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
