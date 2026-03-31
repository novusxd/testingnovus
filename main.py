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
    print(f"❌ ERROR: Konfigurasi .env bermasalah! | {e}")
    exit()

# ID STIKER WATERMARK
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State user (0: Chat Biasa, 1: Mode Donasi)
user_states = {}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    first_name = message.from_user.first_name
    teks = (
        f"👋 **Halo {first_name}!**\n\n"
        "Selamat datang di **Testing Novus Bot**. 🛡️\n"
        "Gunakan tombol di bawah untuk donasi media."
    )
    await message.reply_text(
        teks,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Mulai Donasi Sekarang", callback_data="start_donasi")],
            [InlineKeyboardButton("🌐 Website Novus", url="https://novus.web.id")]
        ])
    )

@app.on_callback_query(filters.regex("start_donasi"))
async def donasi_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_states[user_id] = 1
    await callback_query.message.reply("📸 **MODE DONASI AKTIF**\n\nKirimkan Foto/Video Anda sekarang.")
    await callback_query.answer()

@app.on_message(filters.private & ~filters.command("start"))
async def handle_messages(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id, 0)

    # --- LOGIKA ADMIN BALAS MEMBER (Sesuai Permintaan Anda) ---
    if user_id == DEVS and message.reply_to_message:
        target_id = None
        
        # 1. Cek dari Metadata Forward (Diteruskan dari...)
        if message.reply_to_message.forward_from:
            target_id = message.reply_to_message.forward_from.id
        
        # 2. Cek dari Teks Info (Jika profil member diprivat)
        else:
            try:
                txt = message.reply_to_message.text or message.reply_to_message.caption
                if "🆔 ID: `" in txt:
                    target_id = int(txt.split("🆔 ID: `")[1].split("`")[0])
            except:
                pass

        if target_id:
            try:
                await client.copy_message(
                    chat_id=target_id,
                    from_chat_id=message.chat.id,
                    message_id=message.id,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Lagi", callback_data="start_donasi")]])
                )
                await message.reply_text(f"✅ Terbalas ke `{target_id}`")
                return
            except Exception as e:
                await message.reply_text(f"❌ Gagal: {e}")
                return
        else:
            await message.reply_text("❌ Gagal: Reply pesan 'Diteruskan dari' atau pesan info ID dari bot.")
            return

    # --- LOGIKA MEMBER KIRIM MEDIA DONASI ---
    if state == 1:
        if not (message.photo or message.video):
            await message.reply("⚠️ Kirim Foto atau Video saja.")
            return

        status = await message.reply("⏳ **Memproses...**")
        file_p = await message.download()
        out_p = f"output_{os.path.basename(file_p)}"
        stk_p = await client.download_media(STICKER_ID)

        try:
            if message.photo:
                img = Image.open(file_p).convert("RGB")
                stk = Image.open(stk_p).convert("RGBA")
                stk = stk.resize((img.width // 3, int(stk.height * (img.width // 3 / stk.width))), Image.LANCZOS)
                img.paste(stk, ((img.width - stk.width)//2, (img.height - stk.height)//2), stk)
                img.save(out_p, "JPEG", quality=90)
                await client.send_photo(DB_CHANNEL_ID, out_p, caption=f"📥 **DONASI FOTO**\n👤 User: `{user_id}`\n📝 {message.caption or '-'}")

            elif message.video:
                clip = me.VideoFileClip(file_p)
                logo = (me.ImageClip(stk_p).set_duration(clip.duration).resize(height=clip.h // 4).set_pos("center"))
                final = me.CompositeVideoClip([clip, logo])
                final.write_videofile(out_p, codec="libx264", audio_codec="aac", logger=None)
                clip.close()
                await client.send_video(DB_CHANNEL_ID, out_p, caption=f"📥 **DONASI VIDEO**\n👤 User: `{user_id}`\n📝 {message.caption or '-'}")

            await message.reply("✅ Donasi terkirim ke Database!")
            user_states[user_id] = 0
        except Exception as e:
            logging.error(e)
            await message.reply(f"❌ Error: {e}")
        finally:
            for f in [file_p, out_p, stk_p]:
                if f and os.path.exists(f): os.remove(f)
            await status.delete()
        return

    # --- LOGIKA MEMBER CHAT KE ADMIN ---
    if user_id != DEVS:
        # Pesan 1: Meneruskan pesan asli member agar muncul "Diteruskan dari..."
        await message.forward(DEVS)
        
        # Pesan 2: Informasi ID (Sebagai cadangan jika profil member privat)
        info = f"📩 **Pesan Baru**\n👤 Member: {message.from_user.mention}\n🆔 ID: `{user_id}`"
        await client.send_message(DEVS, info)

print("🚀 Bot Siap Beraksi!")
app.run()
