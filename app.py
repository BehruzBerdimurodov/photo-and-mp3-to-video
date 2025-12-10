import os
import logging
import sqlite3
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip
from pydub import AudioSegment
from PIL import Image

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- PATCH: Pillow Compatibility ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# --- CONFIG ---
TOKEN = "858160775:AAFAoUppwpZ-JYl_SmFd6jR-65T5mqxZh74" 

# --- HELPER FUNCTIONS ---

def clean_temp_files(user_id):
    """Foydalanuvchiga tegishli vaqtinchalik fayllarni o'chirish"""
    try:
        for file in os.listdir():
            if (file.startswith(f"temp_{user_id}") or file.startswith(f"output_{user_id}")) and file != "bot_data.db":
                try:
                    os.remove(file)
                except PermissionError:
                    pass 
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def parse_time(time_str):
    parts = time_str.split(':')
    try:
        if len(parts) == 1: return float(parts[0])
        elif len(parts) == 2: return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3: return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        else: raise ValueError
    except ValueError:
        raise ValueError("Vaqt xato")

def prepare_image(image_path):
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w % 2 != 0: w -= 1
        if h % 2 != 0: h -= 1
        if w != img.size[0] or h != img.size[1]:
            img = img.resize((w, h), Image.Resampling.LANCZOS)
        img.save(image_path, format="JPEG", quality=95)
    return image_path

# --- DB FUNCTIONS ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, language TEXT)''')
    conn.commit()
    conn.close()

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

# --- TEXTS ---
TEXTS = {
    'uz': {
        'welcome': "Assalomu alaykum! 👋\n\nMenyudan yoki buyruqlardan foydalaning:\n\n/photo_to_video - Rasm → Video\n/video_to_mp3 - Video → MP3\n/cut_video - Videoni qirqish\n/mute_video - Videoni ovozsiz qilish\n/add_audio - Videoga ovoz qo'shish\n/lang - Tilni o'zgartirish",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'main_menu': "Quyidagi funksiyalardan birini tanlang:",
        'btn_photo_video': "🎬 Rasm + Audio → Video",
        'btn_video_mp3': "🎵 Video → MP3",
        'btn_video_cut': "✂️ Videoni qirqish",
        'btn_mute': "🔇 Videoni ovozsiz qilish",
        'btn_add_audio': "🔉 Videoga ovoz qo'shish",
        'btn_lang': "🌐 Tilni o'zgartirish",
        'send_photo': "Iltimos, rasm yuboring 📸",
        'send_video': "Iltimos, video yuboring 🎬",
        'send_audio': "Endi audio yoki ovozli xabar yuboring 🎵",
        'send_video_for_audio': "Qaysi videoga ovoz qo'shmoqchisiz? Videoni yuboring 🎬",
        'send_audio_for_video': "Video qabul qilindi. Endi unga qo'yiladigan audioni yuboring 🎵",
        'video_cut_instr': "Video qabul qilindi. Qirqish vaqtini 'START-END' formatida yozing (Masalan: 10-25) ⏱",
        'processing': "⏳ Jarayon ketmoqda... {}%",
        'ready': "✅ Tayyor!",
        'error': "❌ Xatolik: {}",
        'invalid_time': "❌ Vaqt formati noto'g'ri!",
    },
    'ru': {
        'welcome': "Здравствуйте! 👋\n\nИспользуйте меню или команды:\n\n/photo_to_video - Фото → Видео\n/video_to_mp3 - Видео → MP3\n/cut_video - Обрезка видео\n/mute_video - Убрать звук\n/add_audio - Добавить звук\n/lang - Язык",
        'choose_lang': "Tilni tanlang / Выберите язык",
        'main_menu': "Выберите одну из функций ниже:",
        'btn_photo_video': "🎬 Фото + Аудио → Видео",
        'btn_video_mp3': "🎵 Видео → MP3",
        'btn_video_cut': "✂️ Обрезка видео",
        'btn_mute': "🔇 Убрать звук из видео",
        'btn_add_audio': "🔉 Добавить звук в видео",
        'btn_lang': "🌐 Изменить язык",
        'send_photo': "Пожалуйста, отправьте фото 📸",
        'send_video': "Пожалуйста, отправьте видео 🎬",
        'send_audio': "Теперь отправьте аудио или голосовое сообщение 🎵",
        'send_video_for_audio': "Отправьте видео, к которому нужно добавить звук 🎬",
        'send_audio_for_video': "Видео получено. Теперь отправьте аудио файл 🎵",
        'video_cut_instr': "Видео получено. Напишите время обрезки в формате 'START-END' (Например: 10-25) ⏱",
        'processing': "⏳ Обработка... {}%",
        'ready': "✅ Готово!",
        'error': "❌ Ошибка: {}",
        'invalid_time': "❌ Неверный формат времени!",
    }
}

user_data = {}

# --- KEYBOARDS ---
def get_main_keyboard(lang):
    kb = [
        [KeyboardButton(TEXTS[lang]['btn_photo_video']), KeyboardButton(TEXTS[lang]['btn_video_mp3'])],
        [KeyboardButton(TEXTS[lang]['btn_mute']), KeyboardButton(TEXTS[lang]['btn_add_audio'])],
        [KeyboardButton(TEXTS[lang]['btn_video_cut']), KeyboardButton(TEXTS[lang]['btn_lang'])]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- TASKS ---
def task_photo_to_video(photo_path, audio_path, output_path):
    try:
        clean_photo = prepare_image(photo_path)
        audio = AudioFileClip(audio_path)
        video = ImageClip(clean_photo, duration=audio.duration)
        video = video.set_audio(audio)
        video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', preset='fast', logger=None)
        video.close(); audio.close()
    except Exception as e:
        logger.error(e); raise e

def task_video_cut(video_path, start, end, output_path):
    try:
        clip = VideoFileClip(video_path)
        if end > clip.duration: end = clip.duration
        sub = clip.subclip(start, end)
        sub.write_videofile(output_path, codec='libx264', audio_codec='aac', preset='fast', logger=None)
        clip.close(); sub.close()
    except Exception as e:
        logger.error(e); raise e

def task_video_to_mp3(video_path, audio_output):
    try:
        clip = VideoFileClip(video_path)
        clip.audio.write_audiofile(audio_output, logger=None)
        clip.close()
    except Exception as e:
        logger.error(e); raise e

def task_mute_video(video_path, output_path):
    try:
        clip = VideoFileClip(video_path)
        new_clip = clip.without_audio()
        new_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', preset='fast', logger=None)
        clip.close(); new_clip.close()
    except Exception as e:
        logger.error(e); raise e

def task_add_audio_to_video(video_path, audio_path, output_path):
    try:
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)
        if audio.duration > video.duration: audio = audio.subclip(0, video.duration)
        final_video = video.set_audio(audio)
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', preset='fast', logger=None)
        video.close(); audio.close(); final_video.close()
    except Exception as e:
        logger.error(e); raise e

# --- COMMAND HANDLERS (SLASH COMMANDS) ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    if lang:
        user_data[user_id] = {'step': 'menu', 'lang': lang}
        await update.message.reply_text(TEXTS[lang]['welcome'], reply_markup=get_main_keyboard(lang))
    else:
        kb = [[InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='uz'), InlineKeyboardButton("🇷🇺 Русский", callback_data='ru')]]
        await update.message.reply_text(TEXTS['uz']['choose_lang'], reply_markup=InlineKeyboardMarkup(kb))

async def cmd_photo_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    user_data[user_id] = {'step': 'pv_wait_photo', 'lang': lang}
    await update.message.reply_text(TEXTS[lang]['send_photo'])

async def cmd_video_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    user_data[user_id] = {'step': 'v2m_wait_video', 'lang': lang}
    await update.message.reply_text(TEXTS[lang]['send_video'])

async def cmd_cut_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    user_data[user_id] = {'step': 'cut_wait_video', 'lang': lang}
    await update.message.reply_text(TEXTS[lang]['send_video'])

async def cmd_mute_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    user_data[user_id] = {'step': 'mute_wait_video', 'lang': lang}
    await update.message.reply_text(TEXTS[lang]['send_video'])

async def cmd_add_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    user_data[user_id] = {'step': 'add_wait_video', 'lang': lang}
    await update.message.reply_text(TEXTS[lang]['send_video_for_audio'])

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    kb = [[InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='uz'), InlineKeyboardButton("🇷🇺 Русский", callback_data='ru')]]
    await update.message.reply_text(TEXTS[lang]['choose_lang'], reply_markup=InlineKeyboardMarkup(kb))

# --- BUTTON HANDLER ---

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    text = update.message.text
    
    # Text commands to logic mapping
    if text == TEXTS[lang]['btn_photo_video']: await cmd_photo_to_video(update, context)
    elif text == TEXTS[lang]['btn_video_mp3']: await cmd_video_to_mp3(update, context)
    elif text == TEXTS[lang]['btn_video_cut']: await cmd_cut_video(update, context)
    elif text == TEXTS[lang]['btn_mute']: await cmd_mute_video(update, context)
    elif text == TEXTS[lang]['btn_add_audio']: await cmd_add_audio(update, context)
    elif text == TEXTS[lang]['btn_lang']: await cmd_lang(update, context)
    else:
        # Agar "Video qirqish vaqti" kutilayotgan bo'lsa
        if user_data.get(user_id, {}).get('step') == 'cut_wait_time':
            await handle_cut_text(update, context)
        else:
            await update.message.reply_text(TEXTS[lang]['main_menu'], reply_markup=get_main_keyboard(lang))

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    set_user_language(query.from_user.id, lang)
    user_data[query.from_user.id] = {'step': 'menu', 'lang': lang}
    await query.delete_message()
    await context.bot.send_message(query.from_user.id, TEXTS[lang]['welcome'], reply_markup=get_main_keyboard(lang))

# --- MEDIA HANDLERS ---
# (Bu qism oldingi kod bilan deyarli bir xil, faqat handler nomlari)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_data.get(user_id, {})
    lang = state.get('lang', 'uz')
    if state.get('step') == 'pv_wait_photo':
        clean_temp_files(user_id)
        f = await update.message.photo[-1].get_file()
        path = f"temp_{user_id}_p.jpg"
        await f.download_to_drive(path)
        user_data[user_id]['photo_path'] = path
        user_data[user_id]['step'] = 'pv_wait_audio'
        await update.message.reply_text(TEXTS[lang]['send_audio'])

async def handle_audio_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_data.get(user_id, {})
    lang = state.get('lang', 'uz')
    step = state.get('step')
    if step not in ['pv_wait_audio', 'add_wait_audio']: return

    msg = await update.message.reply_text(TEXTS[lang]['processing'].format(10))
    try:
        f = await (update.message.audio.get_file() if update.message.audio else update.message.voice.get_file())
        ext = 'mp3' if update.message.audio else 'ogg'
        audio_path = f"temp_{user_id}_a.{ext}"
        await f.download_to_drive(audio_path)

        if ext == 'ogg':
            mp3_path = f"temp_{user_id}_a.mp3"
            await asyncio.to_thread(lambda: AudioSegment.from_ogg(audio_path).export(mp3_path, format="mp3"))
            if os.path.exists(audio_path): os.remove(audio_path)
            audio_path = mp3_path
        
        output_path = f"output_{user_id}.mp4"
        if step == 'pv_wait_audio':
            await msg.edit_text(TEXTS[lang]['processing'].format(50))
            await asyncio.to_thread(task_photo_to_video, state['photo_path'], audio_path, output_path)
        elif step == 'add_wait_audio':
            await msg.edit_text(TEXTS[lang]['processing'].format(50))
            await asyncio.to_thread(task_add_audio_to_video, state['video_path'], audio_path, output_path)

        await msg.edit_text(TEXTS[lang]['processing'].format(100))
        with open(output_path, 'rb') as v: await update.message.reply_video(v, caption=TEXTS[lang]['ready'])
        await msg.delete()
    except Exception as e: await msg.edit_text(TEXTS[lang]['error'].format(str(e)))
    finally: clean_temp_files(user_id); user_data[user_id]['step'] = 'menu'

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_data.get(user_id, {})
    lang = state.get('lang', 'uz')
    step = state.get('step')
    if step not in ['v2m_wait_video', 'cut_wait_video', 'mute_wait_video', 'add_wait_video']: return

    clean_temp_files(user_id)
    msg = await update.message.reply_text(TEXTS[lang]['processing'].format(10))
    try:
        f = await update.message.video.get_file()
        video_path = f"temp_{user_id}_v.mp4"
        await f.download_to_drive(video_path)

        if step == 'v2m_wait_video':
            out = f"output_{user_id}.mp3"
            await asyncio.to_thread(task_video_to_mp3, video_path, out)
            with open(out, 'rb') as a: await update.message.reply_audio(a, caption=TEXTS[lang]['ready'])
            await msg.delete()
            clean_temp_files(user_id); user_data[user_id]['step'] = 'menu'
        elif step == 'mute_wait_video':
            out = f"output_{user_id}.mp4"
            await asyncio.to_thread(task_mute_video, video_path, out)
            with open(out, 'rb') as v: await update.message.reply_video(v, caption=TEXTS[lang]['ready'])
            await msg.delete()
            clean_temp_files(user_id); user_data[user_id]['step'] = 'menu'
        elif step == 'cut_wait_video':
            user_data[user_id].update({'video_path': video_path, 'step': 'cut_wait_time'})
            await msg.delete(); await update.message.reply_text(TEXTS[lang]['video_cut_instr'])
        elif step == 'add_wait_video':
            user_data[user_id].update({'video_path': video_path, 'step': 'add_wait_audio'})
            await msg.delete(); await update.message.reply_text(TEXTS[lang]['send_audio_for_video'])
    except Exception as e: await msg.edit_text(TEXTS[lang]['error'].format(str(e))); clean_temp_files(user_id)

async def handle_cut_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_data.get(user_id, {})
    lang = state.get('lang', 'uz')
    if not state.get('video_path'): return
    msg = await update.message.reply_text(TEXTS[lang]['processing'].format(20))
    try:
        start_t, end_t = map(lambda x: parse_time(x.strip()), update.message.text.split('-'))
        output_path = f"output_{user_id}.mp4"
        await asyncio.to_thread(task_video_cut, state['video_path'], start_t, end_t, output_path)
        with open(output_path, 'rb') as v: await update.message.reply_video(v, caption=TEXTS[lang]['ready'])
        await msg.delete()
    except Exception as e: await msg.edit_text(TEXTS[lang]['error'].format(str(e)))
    finally: clean_temp_files(user_id); user_data[user_id]['step'] = 'menu'

# --- MAIN ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    # 1. Buyruqlar (Commands)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("photo_to_video", cmd_photo_to_video))
    app.add_handler(CommandHandler("video_to_mp3", cmd_video_to_mp3))
    app.add_handler(CommandHandler("cut_video", cmd_cut_video))
    app.add_handler(CommandHandler("mute_video", cmd_mute_video))
    app.add_handler(CommandHandler("add_audio", cmd_add_audio))
    app.add_handler(CommandHandler("lang", cmd_lang))

    # 2. Tugma bosilganda (Text)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))
    app.add_handler(CallbackQueryHandler(lang_callback))
    
    # 3. Media fayllar
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_voice))
    
    logger.info("Bot ishga tushdi...")
    app.run_polling()

if __name__ == '__main__':
    main()
