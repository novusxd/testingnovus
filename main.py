import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID"))
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: Pastikan variabel .env sudah benar! | {e}")
    exit()

# ID STIKER WATERMARK
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Memori Internal
forwarded_messages = {} # Untuk reply admin
waiting_caption = {}    # Untuk menyimpan media sementara yang menunggu caption

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text(
        f"👋 **Halo {message.from_user.first_name}!**\n\n"
        "Selamat datang di **Testing Novus Bot**.\n"
        "Kirimkan foto atau video untuk donasi ke database.\n\n"
        "⚠️ **Catatan:** Setiap media wajib memiliki caption/deskripsi."
    )

# --- FUNGSI PROSES MEDIA (Watermark & Send) ---
async def process_and_send(client, user_id, message_obj, caption_text):
    status = await client.send_message(user_id, "⏳ **Sedang memproses watermark...**")
    
    # Download media dari pesan asli
    file_p = await message_obj.download()
    out_p = f"final_{os.path.basename(file_p)}"
    stk_p = await client.download_media(STICKER_ID)

    try:
        if message_obj.photo:
            img = Image.open(file_p).convert("RGB")
            stk = Image.open(stk_p).convert("RGBA")
            stk = stk.resize((img.width // 3, int(stk.height * (img.width // 3 / stk.width))), Image.LANCZOS)
            img.paste(stk, ((img.width - stk.width)//2, (img.height - stk.height)//2), stk)
            img.save(out_p, "JPEG", quality=90)
            await client.send_photo(chat_id=DB_CHANNEL_ID, photo=out_p, caption=caption_text)

        elif message_obj.video:
            clip = me.VideoFileClip(file_p)
            logo = (me.ImageClip(stk_p).set_duration(clip.duration).resize(height=clip.h // 4).set_pos("center"))
            final = me.CompositeVideoClip([clip, logo])
            final.write_videofile(out_p, codec="libx264", audio_codec="aac", logger=None)
            clip.close()
            await client.send_video(chat_id=DB_CHANNEL_ID, video=out_p, caption=caption_text)

        await status.edit("✅ **Berhasil!** Media telah ber-watermark dan terkirim ke database.")
        
        # Teruskan ke Admin sebagai laporan
        info = await message_obj.forward(DEVS)
        forwarded_messages[info.id] = user_id
        await client.send_message(DEVS, f"📥 **Donasi Baru dari {message_obj.from_user.mention}**\nID: `{user_id}`\n📝 Caption: {caption_text}")

    except Exception as e:
        logging.error(e)
        await status.edit(f"❌ Gagal memproses: {e}")
    finally:
        for f in [file_p, out_p, stk_p]:
            if f and os.path.exists(f): os.remove(f)

# --- HANDLER UTAMA ---
@app.on_message(filters.private & ~filters.command("start"))
async def handle_everything(client, message):
    user_id = message.from_user.id

    # 1. LOGIKA ADMIN BALAS MEMBER
    if user_id == DEVS and message.reply_to_message:
        target_id = forwarded_messages.get(message.reply_to_message.id)
        if target_id:
            try:
                await client.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.id)
                await message.reply_text(f"✅ Terbalas ke `{target_id}`")
            except Exception as e:
                await message.reply_text(f"❌ Gagal balas: {e}")
        return

    # 2. LOGIKA MENERIMA CAPTION SUSULAN
    if user_id in waiting_caption and message.text:
        media_msg = waiting_caption.pop(user_id) # Ambil media yang disimpan tadi
        await process_and_send(client, user_id, media_msg, message.text)
        return

    # 3. LOGIKA MEMBER KIRIM MEDIA
    if message.photo or message.video:
        if message.caption:
            # Jika sudah ada caption, langsung proses
            await process_and_send(client, user_id, message, message.caption)
        else:
            # Jika tidak ada caption, simpan pesan media dan minta teks
            waiting_caption[user_id] = message
            await message.reply_text("⚠️ **Media terdeteksi tanpa caption!**\n\nSilakan ketikkan deskripsi/caption untuk foto/video ini agar bisa saya proses.")
        return

    # 4. LOGIKA CHAT TEXT BIASA
    if user_id != DEVS:
        fw = await message.forward(DEVS)
        forwarded_messages[fw.id] = user_id
        await client.send_message(DEVS, f"📩 **Pesan dari {message.from_user.mention}**\nID: `{user_id}`")

print("🚀 Bot Siap! Sistem Antrean Caption Aktif.")
app.run()
