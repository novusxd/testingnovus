import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me

load_dotenv()

# Konfigurasi
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEVS = int(os.getenv("DEVS"))
DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID"))
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("donasi_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State sederhana untuk user (0: Chat, 1: Menunggu Media Donasi)
user_states = {}

@app.on_message(filters.private & ~filters.command("start"))
async def handle_messages(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id, 0)

    # Logika Admin Balas Member
    if user_id == DEVS and message.reply_to_message:
        target_id = message.reply_to_message.forward_from.id if message.reply_to_message.forward_from else None
        if not target_id:
            # Mencari ID dari teks jika forward_from disembunyikan
            try: target_id = int(message.reply_to_message.caption.split("ID: ")[1])
            except: return
        
        await client.copy_message(target_id, message.chat.id, message.id, 
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]]))
        return

    # Logika Member Kirim Donasi (State 1)
    if state == 1:
        msg = await message.reply("⏳ Sedang memproses media donasi...")
        file_path = await message.download()
        output_path = f"watermarked_{os.path.basename(file_path)}"
        sticker_path = await client.download_media(STICKER_ID)

        try:
            if message.photo:
                img = Image.open(file_path)
                stk = Image.open(sticker_path).convert("RGBA")
                stk = stk.resize((img.width // 3, img.width // 3)) # Proporsional
                img.paste(stk, ((img.width - stk.width)//2, (img.height - stk.height)//2), stk)
                img.save(output_path)
                await client.send_photo(DB_CHANNEL_ID, output_path, caption=f"Donasi dari: {user_id}\nCaption: {message.caption or 'Tanpa Caption'}")
            
            elif message.video:
                video = me.VideoFileClip(file_path)
                logo = (me.ImageClip(sticker_path)
                        .set_duration(video.duration)
                        .resize(height=video.h // 4)
                        .set_pos("center"))
                final = me.CompositeVideoClip([video, logo])
                final.write_videofile(output_path, codec="libx264")
                await client.send_video(DB_CHANNEL_ID, output_path, caption=f"Donasi dari: {user_id}\nCaption: {message.caption or 'Tanpa Caption'}")

            await message.reply("✅ Donasi Anda telah terkirim ke Database. Terima kasih!")
            user_states[user_id] = 0 # Kembali ke mode chat
        finally:
            # Hapus file dari VPS
            for f in [file_path, output_path, sticker_path]:
                if os.path.exists(f): os.remove(f)
            await msg.delete()
        return

    # Logika Member Chat ke Admin (State 0)
    if user_id != DEVS:
        await message.forward(DEVS)
        await client.send_message(DEVS, f"⬆️ Pesan di atas dari ID: `{user_id}`\nBalas pesan di atas untuk merespon.")

@app.on_callback_query(filters.regex("start_donasi"))
async def donasi_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_states[user_id] = 1
    await callback_query.message.reply("📸 Silakan kirimkan Media (Foto/Video) beserta caption donasi Anda.")
    await callback_query.answer()

app.run()
