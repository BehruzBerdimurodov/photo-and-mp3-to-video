import os
import logging
import sqlite3
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip, ColorClip, CompositeVideoClip
from pydub import AudioSegment
from PIL import Image

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- PATCH: Pillow & MoviePy Compatibility ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# --- CONFIG ---
# Xavfsizlik uchun tokenni shu yerga qo'ying yoki Environment Variable dan oling
TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74" 

# --- HELPER FUNCTIONS ---

def parse_time(time_str):
    """Vaqtni sekundlarga o'giradi (10, 0:30, 1:05)"""
    parts = time_str.split(':')
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
        elif len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        else:
            raise ValueError
    except ValueError:
        raise ValueError("Vaqt formati noto'g'ri")

def prepare_image(image_path):
    """
    Rasmni videoga tayyorlash:
    1. RGB ga o'tkazish.
    2. O'lchamlarni juft songa keltirish (H.264 talabi).
    """
    with Image.open(image_path) as img:
        img = img.convert("RGB") # CMYK yoki RGBA muammosini hal qiladi
        w, h = img.size
        
        # O'lchamlar juft bo'lishi shart
        if w % 2 != 0: w -= 1
        if h % 2 != 0: h -= 1
        
        # Agar o'lcham o'zgargan bo'lsa, qayta saqlaymiz
        if w != img.size[0] or h != img.size[1]:
            img = img.resize((w, h), Image.Resampling.LANCZOS)
        
        img.save(image_path, format="JPEG", quality=95)
    return image_path

def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, language TEXT)''')
    conn.commit()
    conn.close()

# --- TEXTS ---
TEXTS = {
    'uz': {
        'welcome': "Assalomu alaykum! 👋\n\nIltimos, tilni tanlang:",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'lang_selected': "✅ Til tanlandi: O'zbekcha\n\nQuyidagi funksiyalardan birini tanlang:",
        'main_menu': "Quyidagi funksiyalardan birini tanlang:",
        'photo_to_video': "🎬 Rasm + Audio → Video",
        'video_to_mp3': "🎵 Video → MP3",
        'video_cut': "✂️ Videoni qirqish",
        'change_language': "🌐 Tilni o'zgartirish",
        'send_photo': "Iltimos, rasm yuboring 📸",
        'photo_received': "Rasm qabul qilindi ✅\n\nEndi audio fayl yoki ovozli xabar yuboring 🎵",
        'send_video': "Iltimos, video yuboring 🎬",
        'video_received': "Video qabul qilindi ✅\n\nMP3 ga aylantirilmoqda...",
        'video_received_cut': "Video qabul qilindi ✅\n\nEndi qirqish vaqtlarini 'START-END' formatida yuboring (Masalan: 10-25 yoki 0:30-1:05) ⏱️",
        'processing': "⏳ Jarayon: {}%",
        'complete': "✅ Tayyor!",
        'video_ready': "✅ Tayyor! Video muvaffaqiyatli tayyorlandi!",
        'audio_ready': "✅ Tayyor! MP3 muvaffaqiyatli tayyorlandi",
        'send_again': "\n\nYana ishlash uchun menyudan foydalaning 🔄",
        'error': "❌ Xatolik yuz berdi: {}\n\nQaytadan urinib ko'ring.",
        'invalid_time': "❌ Vaqt formati noto'g'ri. Masalan: 00:10-00:30",
        'start_first': "Iltimos /start ni bosing!",
    },
    'ru': {
        'welcome': "Здравствуйте! 👋\n\nПожалуйста, выберите язык:",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'lang_selected': "✅ Язык выбран: Русский\n\nВыберите одну из функций ниже:",
        'main_menu': "Выберите одну из функций ниже:",
        'photo_to_video': "🎬 Фото + Аудио → Видео",
        'video_to_mp3': "🎵 Видео → MP3",
        'video_cut': "✂️ Обрезка видео",
        'change_language': "🌐 Изменить язык",
        'send_photo': "Пожалуйста, отправьте фото 📸",
        'photo_received': "Фото получено ✅\n\nТеперь отправьте аудио файл или голосовое сообщение 🎵",
        'send_video': "Пожалуйста, отправьте видео 🎬",
        'video_received': "Видео получено ✅\n\nКонвертация в MP3...",
        'video_received_cut': "Видео получено ✅\n\nТеперь отправьте время обрезки в формате 'START-END' (Например: 10-25 или 0:30-1:05) ⏱️",
        'processing': "⏳ Процесс: {}%",
        'complete': "✅ Готово!",
        'video_ready': "✅ Готово! Видео успешно сформировано",
        'audio_ready': "✅ Готово! MP3 успешно подготовлен",
        'send_again': "\n\nДля продолжения используйте меню 🔄",
        'error': "❌ Произошла ошибка: {}\n\nПопробуйте снова.",
        'invalid_time': "❌ Неверный формат времени. Пример: 00:10-00:30",
        'start_first': "Пожалуйста, нажмите /start!",
    }
}

user_data = {}

# --- DB FUNCTIONS ---
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
    c.execute("INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)", (user_id, language))
    conn.commit()
    conn.close()

def delete_user_files(user_id):
    """Foydalanuvchining eski temp fayllarini tozalash"""
    for file in os.listdir():
        if file.startswith(f"temp_{user_id}") or file.startswith(f"output_{user_id}"):
            try:
                os.remove(file)
            except Exception:
                pass

def get_main_keyboard(lang):
    keyboard = [
        [KeyboardButton(TEXTS[lang]['photo_to_video'])],
        [KeyboardButton(TEXTS[lang]['video_to_mp3']), KeyboardButton(TEXTS[lang]['video_cut'])],
        [KeyboardButton(TEXTS[lang]['change_language'])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- PROCESSING FUNCTIONS (IN THREADS) ---

def process_video_cut(video_path, start_time, end_time, output_path):
    """Video qirqish - Blocking function wrapper"""
    try:
        clip = VideoFileClip(video_path)
        if end_time > clip.duration:
            end_time = clip.duration
        
        subclip = clip.subclip(start_time, end_time)
        
        # MUHIM: audio_codec='aac' va pixel_format='yuv420p'
        subclip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            pixel_format='yuv420p',  # TELEFONDA OCHISH UCHUN SHART
            preset='medium',
            logger=None
        )
        subclip.close()
        clip.close()
        return True
    except Exception as e:
        logger.error(f"Cut Error: {e}")
        raise e

def process_photo_to_video(photo_path, audio_path, output_path):
    """Rasm + Audio -> Video - Blocking function wrapper"""
    try:
        # Rasmni to'g'irlash
        clean_photo_path = prepare_image(photo_path)
        
        audio = AudioFileClip(audio_path)
        image = ImageClip(clean_photo_path, duration=audio.duration)
        
        # Agar rasm juda katta bo'lsa, uni kichraytirish (HD)
        # image = image.resize(height=720) # Ixtiyoriy: sifatni saqlash uchun o'chirildi, lekin o'lcham juft bo'lishi shart
        
        video = image.set_audio(audio)
        
        # MUHIM SOZLAMALAR
        video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            pixel_format='yuv420p', # TELEFONDA OCHISH UCHUN SHART
            preset='medium',
            threads=4,
            logger=None
        )
        video.close()
        audio.close()
        return True
    except Exception as e:
        logger.error(f"Photo2Video Error: {e}")
        raise e

def process_video_to_mp3(video_path, audio_output):
    """Video -> MP3 - Blocking function wrapper"""
    try:
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_output, logger=None)
        video.close()
        return True
    except Exception as e:
        logger.error(f"MP3 Error: {e}")
        raise e

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    
    if lang:
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        await update.message.reply_text(TEXTS[lang]['main_menu'], reply_markup=get_main_keyboard(lang))
    else:
        keyboard = [[InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz'),
                     InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')]]
        await update.message.reply_text(TEXTS['uz']['choose_lang'], reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = query.data.split('_')[1]
    
    set_user_language(user_id, lang)
    user_data[user_id] = {'step': 'main_menu', 'lang': lang}
    
    await query.delete_message()
    await context.bot.send_message(user_id, TEXTS[lang]['lang_selected'], reply_markup=get_main_keyboard(lang))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text
    
    # Qirqish vaqtini qabul qilish
    if user_data.get(user_id, {}).get('step') == 'waiting_cut_times':
        return await handle_cut_times(update, context)

    if text == TEXTS[lang]['photo_to_video']:
        user_data[user_id] = {'step': 'waiting_image', 'lang': lang, 'mode': 'photo_to_video'}
        await update.message.reply_text(TEXTS[lang]['send_photo'])
        
    elif text == TEXTS[lang]['video_to_mp3']:
        user_data[user_id] = {'step': 'waiting_video', 'lang': lang, 'mode': 'video_to_mp3'}
        await update.message.reply_text(TEXTS[lang]['send_video'])
        
    elif text == TEXTS[lang]['video_cut']:
        user_data[user_id] = {'step': 'waiting_cut_video', 'lang': lang, 'mode': 'video_cut'}
        await update.message.reply_text(TEXTS[lang]['send_video'])
        
    elif text == TEXTS[lang]['change_language']:
        keyboard = [[InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_uz'),
                     InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')]]
        await update.message.reply_text(TEXTS[lang]['choose_lang'], reply_markup=InlineKeyboardMarkup(keyboard))
        
    else:
        if user_id in user_data:
             await update.message.reply_text(TEXTS[lang]['main_menu'], reply_markup=get_main_keyboard(lang))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_data.get(user_id, {}).get('step') != 'waiting_image':
        await update.message.reply_text(TEXTS[lang]['start_first'])
        return

    delete_user_files(user_id)
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"temp_{user_id}_photo.jpg"
    await photo_file.download_to_drive(photo_path)
    
    user_data[user_id]['photo_path'] = photo_path
    user_data[user_id]['step'] = 'waiting_audio'
    await update.message.reply_text(TEXTS[lang]['photo_received'])

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    
    if user_data.get(user_id, {}).get('step') != 'waiting_audio':
        await update.message.reply_text(TEXTS[lang]['start_first'])
        return
        
    msg = await update.message.reply_text(TEXTS[lang]['processing'].format(0))
    
    try:
        # Download Audio
        if update.message.audio:
            f = await update.message.audio.get_file()
            ext = 'mp3'
        elif update.message.voice:
            f = await update.message.voice.get_file()
            ext = 'ogg'
        else:
            return

        audio_path = f"temp_{user_id}_audio.{ext}"
        await f.download_to_drive(audio_path)
        
        # OGG to MP3 (if voice)
        if ext == 'ogg':
            await msg.edit_text(TEXTS[lang]['processing'].format(20))
            converted_path = f"temp_{user_id}_audio.mp3"
            # Running Pydub in thread to avoid blocking
            await asyncio.to_thread(lambda: AudioSegment.from_ogg(audio_path).export(converted_path, format="mp3"))
            os.remove(audio_path)
            audio_path = converted_path

        await msg.edit_text(TEXTS[lang]['processing'].format(50))
        
        photo_path = user_data[user_id]['photo_path']
        output_path = f"output_{user_id}.mp4"
        
        # RUN HEAVY TASK IN THREAD
        await asyncio.to_thread(process_photo_to_video, photo_path, audio_path, output_path)
        
        await msg.edit_text(TEXTS[lang]['processing'].format(100))
        
        with open(output_path, 'rb') as v:
            await update.message.reply_video(v, caption=TEXTS[lang]['video_ready'])
            
        await msg.delete()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text(TEXTS[lang]['error'].format(str(e)))
    finally:
        delete_user_files(user_id)
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    step = user_data.get(user_id, {}).get('step')
    
    if step not in ['waiting_video', 'waiting_cut_video']:
        return

    delete_user_files(user_id)
    msg = await update.message.reply_text(TEXTS[lang]['processing'].format(10))
    
    try:
        video_file = await update.message.video.get_file()
        video_path = f"temp_{user_id}_video.mp4"
        await video_file.download_to_drive(video_path)
        
        if step == 'waiting_video': # Video to MP3
            output_path = f"output_{user_id}.mp3"
            await msg.edit_text(TEXTS[lang]['processing'].format(50))
            
            # Run in thread
            await asyncio.to_thread(process_video_to_mp3, video_path, output_path)
            
            with open(output_path, 'rb') as a:
                await update.message.reply_audio(a, caption=TEXTS[lang]['audio_ready'])
            
            await msg.delete()
            delete_user_files(user_id)
            user_data[user_id] = {'step': 'main_menu', 'lang': lang}
            
        elif step == 'waiting_cut_video':
            user_data[user_id]['video_path'] = video_path
            user_data[user_id]['step'] = 'waiting_cut_times'
            await msg.delete()
            await update.message.reply_text(TEXTS[lang]['video_received_cut'])
            
    except Exception as e:
        logger.error(f"Video Handle Error: {e}")
        await msg.edit_text(TEXTS[lang]['error'].format(str(e)))
        delete_user_files(user_id)

async def handle_cut_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text
    video_path = user_data.get(user_id, {}).get('video_path')

    if not video_path or not os.path.exists(video_path):
        await update.message.reply_text("Video topilmadi. Qaytadan boshlang.")
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}
        return

    try:
        if '-' not in text: raise ValueError
        start_str, end_str = text.split('-')
        start_t = parse_time(start_str.strip())
        end_t = parse_time(end_str.strip())
        
        if start_t >= end_t: raise ValueError
        
        msg = await update.message.reply_text(TEXTS[lang]['processing'].format(30))
        output_path = f"output_{user_id}_cut.mp4"
        
        # RUN HEAVY TASK IN THREAD
        await asyncio.to_thread(process_video_cut, video_path, start_t, end_t, output_path)
        
        await msg.edit_text(TEXTS[lang]['processing'].format(100))
        
        with open(output_path, 'rb') as v:
            await update.message.reply_video(v, caption=TEXTS[lang]['video_ready'])
            
        await msg.delete()
        
    except ValueError:
        await update.message.reply_text(TEXTS[lang]['invalid_time'])
    except Exception as e:
        logger.error(f"Cut Process Error: {e}")
        await update.message.reply_text(TEXTS[lang]['error'].format(str(e)))
    finally:
        if os.path.exists(f"output_{user_id}_cut.mp4"):
            delete_user_files(user_id)
        user_data[user_id] = {'step': 'main_menu', 'lang': lang}

def main():
    init_db()
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    
    logger.info("Bot ishga tushdi...")
    application.run_polling()

if __name__ == '__main__':
    main()
