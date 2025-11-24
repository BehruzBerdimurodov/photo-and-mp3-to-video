import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip
from pydub import AudioSegment

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def parse_time(time_str):
    """Parses time string (e.g., '10', '0:30', '1:05:00') into seconds (float)."""
    parts = time_str.split(':')
    if not parts:
        raise ValueError("Empty time string")
    
    try:
        # Simple seconds format (e.g., "10")
        if len(parts) == 1:
            return float(parts[0])
        # Minutes and seconds format (e.g., "0:30")
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
        # Hours, minutes, and seconds format (e.g., "1:00:30")
        elif len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        else:
            raise ValueError("Too many time components")
    except ValueError:
        raise ValueError("Time components must be numeric")


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

TEXTS = {
    'uz': {
        'welcome': "Assalomu alaykum! 👋\n\nIltimos, tilni tanlang:",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'lang_selected': "✅ Til tanlandi: O'zbekcha\n\nQuyidagi funksiyalardan birini tanlang:",
        'main_menu': "Quyidagi funksiyalardan birini tanlang:",
        'photo_to_video': "🎬 Rasm + Audio → Video",
        'video_to_mp3': "🎵 Video → MP3",
        'video_cut': "✂️ Videoni qirqish", # New
        'change_language': "🌐 Tilni o'zgartirish",
        'back_to_menu': "🔙 Asosiy menyu",
        'send_photo': "Iltimos, rasm yuboring 📸",
        'photo_received': "Rasm qabul qilindi ✅\n\nEndi audio fayl yoki voice message yuboring 🎵",
        'send_video': "Iltimos, video yuboring 🎬",
        'video_received': "Video qabul qilindi ✅\n\nMP3 ga aylantirilmoqda...",
        'video_received_cut': "Video qabul qilindi ✅\n\nEndi qirqish vaqtlarini 'START-END' formatida yuboring (Masalan: 10-25 yoki 0:30-1:05) ⏱️", # New
        'processing_cut': "⏳ Videoning belgilangan qismi qirqilmoqda...", # New
        'cut_ready': "✅ Tayyor! Video muvaffaqiyatli qirqildi", # New
        'invalid_time_format': "❌ Noto'g'ri vaqt formati. Iltimos, 'START-END' formatida yuboring (Masalan: 10-25 yoki 0:30-1:05)!", # New
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
        'video_cut': "✂️ Обрезка видео", # New
        'change_language': "🌐 Изменить язык",
        'back_to_menu': "🔙 Главное меню",
        'send_photo': "Пожалуйста, отправьте фото 📸",
        'photo_received': "Фото получено ✅\n\nТеперь отправьте аудио файл или голосовое сообщение 🎵",
        'send_video': "Пожалуйста, отправьте видео 🎬",
        'video_received': "Видео получено ✅\n\nКонвертация в MP3...",
        'video_received_cut': "Видео получено ✅\n\nТеперь отправьте время обрезки в формате 'START-END' (Например: 10-25 или 0:30-1:05) ⏱️", # New
        'processing_cut': "⏳ Обрезка видео по указанному времени...", # New
        'cut_ready': "✅ Готово! Видео успешно обрезано", # New
        'invalid_time_format': "❌ Неверный формат времени. Пожалуйста, отправьте в формате 'START-END' (Например: 10-25 или 0:30-1:05)!", # New
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

user_data = {}

def get_user_language(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_user_language(user_id, language):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)",
              (user_id, language))
    conn.commit()
    conn.close()

def save_file_paths(user_id, photo_path=None, audio_path=None, video_path=None):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO files (user_id, photo_path, audio_path, video_path) VALUES (?, ?, ?, ?)",
              (user_id, photo_path, audio_path, video_path))
    conn.commit()
    conn.close()

def delete_old_files(user_id):
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
    c.execute("DELETE FROM files WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_main_keyboard(lang):
    keyboard = [
        [KeyboardButton(TEXTS[lang]['photo_to_video'])],
        [KeyboardButton(TEXTS[lang]['video_to_mp3']), KeyboardButton(TEXTS[lang]['video_cut'])], # Added video_cut
        [KeyboardButton(TEXTS[lang]['change_language'])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    if lang:
        await update.message.reply_text(
            TEXTS[lang]['main_menu'],
            reply_markup=get_main_keyboard(lang)
        )
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
    else:
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

async def handle_cut_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text
    video_path = user_data[user_id].get('video_path')
    
    if not video_path or not os.path.exists(video_path):
        await update.message.reply_text(
            TEXTS[lang]['error'].format("Video fayl topilmadi yoki eskirgan!"),
            reply_markup=get_main_keyboard(lang)
        )
        delete_old_files(user_id)
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        return

    try:
        # Expected format: START-END
        if '-' not in text:
            raise ValueError("Separator '-' not found in time string.")
            
        start_time_str, end_time_str = text.split('-')
        start_time = parse_time(start_time_str.strip())
        end_time = parse_time(end_time_str.strip())

        if start_time < 0 or end_time <= start_time:
            raise ValueError("Vaqtlar noto'g'ri berilgan.")

        # Progress Update 10%
        progress_msg = await update.message.reply_text(TEXTS[lang]['processing'].format(10)) 
        
        # MoviePy processing
        input_clip = VideoFileClip(video_path)
        
        # Check if end_time exceeds clip duration and adjust if necessary
        clip_duration = input_clip.duration
        if end_time > clip_duration:
            end_time = clip_duration
            
        subclip = input_clip.subclip(start_time, end_time)
        
        output_path = f"output_{user_id}_cut.mp4"
        
        # Progress Update 50%
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(50))

        # Write the video file (This is the long operation)
        subclip.write_videofile(
            output_path, 
            codec='libx264',
            audio_codec='aac', 
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            logger=None
        )
        
        subclip.close()
        input_clip.close()

        # Progress Update 90%
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(90))

        # Send the final video
        with open(output_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=TEXTS[lang]['cut_ready']
            )

        # Complete
        await progress_msg.edit_text(TEXTS[lang]['complete'])
        
        # Save output path for deletion and clear state
        save_file_paths(user_id, video_path=output_path) 
        delete_old_files(user_id)
        
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        await update.message.reply_text(
            TEXTS[lang]['send_again'],
            reply_markup=get_main_keyboard(lang)
        )

    except ValueError as ve:
        # Handle parsing errors (invalid time format)
        logger.error(f"Vaqt formati xatosi: {ve}")
        await update.message.reply_text(
            TEXTS[lang]['invalid_time_format']
        )
        # Keep the user in the 'waiting_cut_times' state to try again
    except Exception as e:
        logger.error(f"Video Cut Xatolik: {e}")
        await update.message.reply_text(
            TEXTS[lang]['error'].format(str(e)),
            reply_markup=get_main_keyboard(lang)
        )
        delete_old_files(user_id)
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text

    # Check if the user is in the middle of a cut operation
    if user_id in user_data and user_data[user_id].get('step') == 'waiting_cut_times':
        return await handle_cut_times(update, context)

    if text == TEXTS[lang]['photo_to_video']:
        user_data[user_id] = {'step': 'waiting_image', 'lang': lang, 'mode': 'photo_to_video'}
        await update.message.reply_text(TEXTS[lang]['send_photo'])
    elif text == TEXTS[lang]['video_to_mp3']:
        user_data[user_id] = {'step': 'waiting_video', 'lang': lang, 'mode': 'video_to_mp3'}
        await update.message.reply_text(TEXTS[lang]['send_video'])
    elif text == TEXTS[lang]['video_cut']: # NEW
        user_data[user_id] = {'step': 'waiting_cut_video', 'lang': lang, 'mode': 'video_cut'}
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
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_image':
        await update.message.reply_text(
            TEXTS[lang]['start_first'],
            reply_markup=get_main_keyboard(lang)
        )
        return
    delete_old_files(user_id)
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"temp_{user_id}_photo.jpg"
    await photo_file.download_to_drive(photo_path)
    user_data[user_id]['photo_path'] = photo_path
    user_data[user_id]['step'] = 'waiting_audio'
    await update.message.reply_text(TEXTS[lang]['photo_received'])

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_id not in user_data or user_data[user_id].get('step') not in ['waiting_video', 'waiting_cut_video']:
        await update.message.reply_text(
            TEXTS[lang]['start_first'],
            reply_markup=get_main_keyboard(lang)
        )
        return

    mode = user_data[user_id].get('mode')
    
    if mode == 'video_to_mp3':
        # --- Original Logic for Video to MP3 ---
        try:
            delete_old_files(user_id)
            video_file = await update.message.video.get_file()
            video_path = f"temp_{user_id}_video.mp4"
            await video_file.download_to_drive(video_path)
            progress_msg = await update.message.reply_text(TEXTS[lang]['video_received'])
            
            # Since moviepy doesn't support progress updates easily, we simulate it
            await progress_msg.edit_text(TEXTS[lang]['processing'].format(30)) 
            video = VideoFileClip(video_path)
            audio_output = f"output_{user_id}.mp3"
            
            await progress_msg.edit_text(TEXTS[lang]['processing'].format(60))
            video.audio.write_audiofile(audio_output, logger=None)
            video.close()
            
            await progress_msg.edit_text(TEXTS[lang]['processing'].format(90))
            save_file_paths(user_id, video_path=video_path, audio_path=audio_output)
            
            with open(audio_output, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    caption=TEXTS[lang]['audio_ready']
                )
            
            await progress_msg.edit_text(TEXTS[lang]['complete'])
            delete_old_files(user_id)
            user_data[user_id] = {'step': 'main_menu', 'lang': lang}
            await update.message.reply_text(
                TEXTS[lang]['send_again'],
                reply_markup=get_main_keyboard(lang)
            )
        except Exception as e:
            logger.error(f"MP3 Conversion Xatolik: {e}")
            await update.message.reply_text(
                TEXTS[lang]['error'].format(str(e)),
                reply_markup=get_main_keyboard(lang)
            )
            delete_old_files(user_id)
            user_data[user_id] = {'step': 'main_menu', 'lang': lang}
            
    elif mode == 'video_cut':
        # --- New Logic for Video Cut: Receive video and prompt for times ---
        try:
            delete_old_files(user_id)
            video_file = await update.message.video.get_file()
            video_path = f"temp_{user_id}_video_to_cut.mp4"
            await video_file.download_to_drive(video_path)
            
            # Store the path and update the step
            user_data[user_id]['video_path'] = video_path
            user_data[user_id]['step'] = 'waiting_cut_times'
            
            await update.message.reply_text(
                TEXTS[lang]['video_received_cut']
            )
            
        except Exception as e:
            logger.error(f"Video Cut initial Xatolik: {e}")
            await update.message.reply_text(
                TEXTS[lang]['error'].format(str(e)),
                reply_markup=get_main_keyboard(lang)
            )
            delete_old_files(user_id)
            user_data[user_id] = {'step': 'main_menu', 'lang': lang}


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_audio':
        await update.message.reply_text(
            TEXTS[lang]['send_audio'],
            reply_markup=get_main_keyboard(lang)
        )
        return
    try:
        if update.message.audio:
            audio_file = await update.message.audio.get_file()
            audio_path = f"temp_{user_id}_audio.mp3"
        elif update.message.voice:
            audio_file = await update.message.voice.get_file()
            audio_path = f"temp_{user_id}_voice.ogg"
        else:
            return
        await audio_file.download_to_drive(audio_path)
        progress_msg = await update.message.reply_text(TEXTS[lang]['processing'].format(0))
        if audio_path.endswith('.ogg'):
            await progress_msg.edit_text(TEXTS[lang]['processing'].format(20))
            audio = AudioSegment.from_ogg(audio_path)
            new_audio_path = f"temp_{user_id}_audio.mp3"
            audio.export(new_audio_path, format="mp3")
            os.remove(audio_path)
            audio_path = new_audio_path
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(40))
        photo_path = user_data[user_id]['photo_path']
        output_path = f"output_{user_id}.mp4"
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(60))
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(70))
        image_clip = ImageClip(photo_path, duration=duration)
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(85))
        video = image_clip.set_audio(audio_clip)
        video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            logger=None
        )
        await progress_msg.edit_text(TEXTS[lang]['processing'].format(95))
        save_file_paths(user_id, photo_path, audio_path, output_path)
        with open(output_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=TEXTS[lang]['video_ready']
            )
        await progress_msg.edit_text(TEXTS[lang]['complete'])
        delete_old_files(user_id)
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
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}

def main():
    init_db()
    # The token is provided in the user's input, keep it as is.
    TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74" 
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    # Using handle_video for both video_to_mp3 and video_cut modes
    application.add_handler(MessageHandler(filters.VIDEO, handle_video)) 
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    
    logger.info("Bot ishga tushdi...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Ensure all file paths are correct, this is a modification of the user's provided code.
    main()
