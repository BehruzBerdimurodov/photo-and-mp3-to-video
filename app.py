
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
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Til matnlari
TEXTS = {
    'uz': {
        'welcome': "Assalomu alaykum! 👋\n\nIltimos, tilni tanlang:",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'lang_selected': "✅ Til tanlandi: O'zbekcha\n\nQuyidagi funksiyalardan birini tanlang:",
        'main_menu': "Quyidagi funksiyalardan birini tanlang:",
        'photo_to_video': "🎬 Rasm + Audio → Video",
        'video_to_mp3': "🎵 Video → MP3",
        'change_language': "🌐 Tilni o'zgartirish",
        'back_to_menu': "🔙 Asosiy menyu",
        'send_photo': "Iltimos, rasm yuboring 📸",
        'photo_received': "Rasm qabul qilindi ✅\n\nEndi audio fayl yoki voice message yuboring 🎵",
        'send_video': "Iltimos, video yuboring 🎬",
        'video_received': "Video qabul qilindi ✅\n\nMP3 ga aylantirilmoqda...",
        'send_audio': "Iltimos avval rasm yuboring!",
        'processing': "⏳ Jarayon: {}%",
        'complete': "✅ Jarayon: 100% - Tayyor!",
        'video_ready': "✅ Tayyor! Video muvaffaqiyatli yaratildi",
        'audio_ready': "✅ Tayyor! MP3 muvaffaqiyatli yaratildi",
        'send_again': "\n\nYana ishlash uchun pastdagi tugmalardan foydalaning 🔄",
        'error': "❌ Xatolik yuz berdi: {}\n\nIltimos qaytadan urinib ko'ring.",
        'start_first': "Iltimos /start buyrug'ini bosing!",
        'cancel': "❌ Bekor qilindi. Asosiy menyuga qaytdingiz."
    },
    'ru': {
        'welcome': "Здравствуйте! 👋\n\nПожалуйста, выберите язык:",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'lang_selected': "✅ Язык выбран: Русский\n\nВыберите одну из функций ниже:",
        'main_menu': "Выберите одну из функций ниже:",
        'photo_to_video': "🎬 Фото + Аудио → Видео",
        'video_to_mp3': "🎵 Видео → MP3",
        'change_language': "🌐 Изменить язык",
        'back_to_menu': "🔙 Главное меню",
        'send_photo': "Пожалуйста, отправьте фото 📸",
        'photo_received': "Фото получено ✅\n\nТеперь отправьте аудио файл или голосовое сообщение 🎵",
        'send_video': "Пожалуйста, отправьте видео 🎬",
        'video_received': "Видео получено ✅\n\nКонвертация в MP3...",
        'send_audio': "Пожалуйста, сначала отправьте фото!",
        'processing': "⏳ Процесс: {}%",
        'complete': "✅ Процесс: 100% - Готово!",
        'video_ready': "✅ Готово! Видео успешно создано",
        'audio_ready': "✅ Готово! MP3 успешно создан",
        'send_again': "\n\nДля продолжения работы используйте кнопки ниже 🔄",
        'error': "❌ Произошла ошибка: {}\n\nПожалуйста, попробуйте снова.",
        'start_first': "Пожалуйста, нажмите /start!",
        'cancel': "❌ Отменено. Вы вернулись в главное меню."
    }
}

# Foydalanuvchi ma'lumotlarini saqlash
user_data = {}

def get_user_language(user_id):
    """Foydalanuvchi tilini olish"""
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_user_language(user_id, language):
    """Foydalanuvchi tilini saqlash"""
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)",
              (user_id, language))
    conn.commit()
    conn.close()

def save_file_paths(user_id, photo_path=None, audio_path=None, video_path=None):
    """Fayl yo'llarini bazaga saqlash"""
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO files (user_id, photo_path, audio_path, video_path) VALUES (?, ?, ?, ?)",
              (user_id, photo_path, audio_path, video_path))
    conn.commit()
    conn.close()

def delete_old_files(user_id):
    """Eski fayllarni bazadan va diskdan o'chirish"""
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT photo_path, audio_path, video_path FROM files WHERE user_id=?", (user_id,))
    files = c.fetchall()
    
    for file_row in files:
        for file_path in file_row:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Fayl o'chirildi: {file_path}")
                except Exception as e:
                    logger.error(f"Fayl o'chirishda xatolik: {e}")
    
    # Bazadan yozuvlarni o'chirish
    c.execute("DELETE FROM files WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_main_keyboard(lang):
    """Asosiy menyu klaviaturasi"""
    keyboard = [
        [KeyboardButton(TEXTS[lang]['photo_to_video'])],
        [KeyboardButton(TEXTS[lang]['video_to_mp3'])],
        [KeyboardButton(TEXTS[lang]['change_language'])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ishga tushganda til tanlash"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    
    if lang:
        # Agar til tanlangan bo'lsa, asosiy menyuni ko'rsatish
        await update.message.reply_text(
            TEXTS[lang]['main_menu'],
            reply_markup=get_main_keyboard(lang)
        )
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
    else:
        # Til tanlash tugmalari
        keyboard = [
            [
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz'),
                InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            TEXTS['uz']['choose_lang'],
            reply_markup=reply_markup
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline tugma bosilganda"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data.startswith('lang_'):
        lang = query.data.split('_')[1]
        set_user_language(user_id, lang)
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        
        await query.edit_message_text(TEXTS[lang]['lang_selected'])
        await context.bot.send_message(
            chat_id=user_id,
            text=TEXTS[lang]['main_menu'],
            reply_markup=get_main_keyboard(lang)
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Keyboard tugmalarini boshqarish"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text
    
    if text == TEXTS[lang]['photo_to_video']:
        user_data[user_id] = {'step': 'waiting_image', 'lang': lang, 'mode': 'photo_to_video'}
        await update.message.reply_text(TEXTS[lang]['send_photo'])
        
    elif text == TEXTS[lang]['video_to_mp3']:
        user_data[user_id] = {'step': 'waiting_video', 'lang': lang, 'mode': 'video_to_mp3'}
        await update.message.reply_text(TEXTS[lang]['send_video'])
        
    elif text == TEXTS[lang]['change_language']:
        keyboard = [
            [
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz'),
                InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            TEXTS[lang]['choose_lang'],
            reply_markup=reply_markup
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm qabul qilish"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_image':
        await update.message.reply_text(
            TEXTS[lang]['start_first'],
            reply_markup=get_main_keyboard(lang)
        )
        return
    
    # Eski fayllarni o'chirish
    delete_old_files(user_id)
    
    # Rasmni yuklab olish
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"temp_{user_id}_photo.jpg"
    await photo_file.download_to_drive(photo_path)
    
    user_data[user_id]['photo_path'] = photo_path
    user_data[user_id]['step'] = 'waiting_audio'
    
    await update.message.reply_text(TEXTS[lang]['photo_received'])

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video qabul qilish va MP3 ga aylantirish"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_video':
        await update.message.reply_text(
            TEXTS[lang]['start_first'],
            reply_markup=get_main_keyboard(lang)
        )
        return
    
    try:
        # Eski fayllarni o'chirish
        delete_old_files(user_id)
        
        # Videoni yuklab olish
        video_file = await update.message.video.get_file()
        video_path = f"temp_{user_id}_video.mp4"
        await video_file.download_to_drive(video_path)
        
        progress_msg = await update.message.reply_text(TEXTS[lang]['video_received'])
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(30))
        
        # Videodan audio ajratish
        video = VideoFileClip(video_path)
        audio_output = f"output_{user_id}.mp3"
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(60))
        
        video.audio.write_audiofile(audio_output, logger=None)
        video.close()
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(90))
        
        # Fayl yo'llarini saqlash
        save_file_paths(user_id, video_path=video_path, audio_path=audio_output)
        
        # MP3 ni yuborish
        with open(audio_output, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                caption=TEXTS[lang]['audio_ready']
            )
        
        await progress_msg.edit_text(TEXTS[lang]['complete'])
        
        # Fayllarni o'chirish
        delete_old_files(user_id)
        
        # Asosiy menyuga qaytish
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        await update.message.reply_text(
            TEXTS[lang]['send_again'],
            reply_markup=get_main_keyboard(lang)
        )
        
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await update.message.reply_text(
            TEXTS[lang]['error'].format(str(e)),
            reply_markup=get_main_keyboard(lang)
        )
        delete_old_files(user_id)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio/Voice qabul qilish va video yaratish"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_audio':
        await update.message.reply_text(
            TEXTS[lang]['send_audio'],
            reply_markup=get_main_keyboard(lang)
        )
        return
    
    try:
        # Audio faylni yuklab olish
        if update.message.audio:
            audio_file = await update.message.audio.get_file()
            audio_path = f"temp_{user_id}_audio.mp3"
        elif update.message.voice:
            audio_file = await update.message.voice.get_file()
            audio_path = f"temp_{user_id}_voice.ogg"
        else:
            return
        
        await audio_file.download_to_drive(audio_path)
        
        # Progress xabari
        progress_msg = await update.message.reply_text(TEXTS[lang]['processing'].format(0))
        
        # Voice ni MP3 ga aylantirish
        if audio_path.endswith('.ogg'):
            await progress_msg.edit_text(TEXTS[lang]['processing'].format(20))
            audio = AudioSegment.from_ogg(audio_path)
            new_audio_path = f"temp_{user_id}_audio.mp3"
            audio.export(new_audio_path, format="mp3")
            os.remove(audio_path)
            audio_path = new_audio_path
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(40))
        
        # Video yaratish
        photo_path = user_data[user_id]['photo_path']
        output_path = f"output_{user_id}.mp4"
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(60))
        
        # Audio uzunligini aniqlash
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(70))
        
        # Rasmdan video yaratish
        image_clip = ImageClip(photo_path, duration=duration)
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(85))
        
        # Audio va rasmni birlashtirish
        video = image_clip.set_audio(audio_clip)
        video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            logger=None
        )
        
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(95))
        
        # Fayl yo'llarini bazaga saqlash
        save_file_paths(user_id, photo_path, audio_path, output_path)
        
        # Videoni yuborish
        with open(output_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=TEXTS[lang]['video_ready']
            )
        
        await progress_msg.edit_text(TEXTS[lang]['complete'])
        
        # Fayllarni o'chirish
        delete_old_files(user_id)
        
        # Asosiy menyuga qaytish
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        
        await update.message.reply_text(
            TEXTS[lang]['send_again'],
            reply_markup=get_main_keyboard(lang)
        )
        
    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await update.message.reply_text(
            TEXTS[lang]['error'].format(str(e)),
            reply_markup=get_main_keyboard(lang)
        )
        delete_old_files(user_id)

def main():
    """Botni ishga tushirish"""
    # Ma'lumotlar bazasini yaratish
    init_db()
    
    # Bot tokeningizni bu yerga kiriting
    TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74"

    application = Application.builder().token(TOKEN).build()
    
    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video_message))
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    
    # Botni ishga tushirish
    logger.info("Bot ishga tushdi...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
