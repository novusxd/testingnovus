import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me

# Konfigurasi Logging
logging.basicConfig(level=logging.INFO)

# Memuat konfigurasi dari .env (Gist Terbaru)
load_dotenv()

try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID"))
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: Gagal memuat .env! Pastikan variabel sudah benar. | {e}")
    exit()

# ID STIKER UNTUK WATERMARK (Novus Sticker)
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State user (0: Chat Biasa, 1: Mode Donasi Media)
user_states = {}

# --- FUNGSI START (@TestingNovusBot) ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    first_name = message.from_user.first_name
    teks_sambutan = (
        f"👋 **Halo {first_name}!**\n\n"
        "Selamat datang di **Testing Novus Bot**. 🛡️\n\n"
        "Bot ini adalah pusat layanan komunikasi dan donasi komunitas Novus.\n"
        "✨ **Apa yang bisa Anda lakukan?**\n"
        "💬 **Chat Langsung:** Kirim pesan apa saja, Admin akan membalasnya.\n"
        "📥 **Donasi Konten:** Kirim foto/video untuk meramaikan channel database.\n\n"
        "Klik tombol di bawah jika ingin mulai mengirim media donasi!"
    )
    
    await message.reply_text(
        teks_sambutan,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Mulai Donasi Sekarang", callback_data="start_donasi")],
            [InlineKeyboardButton("🌐 Kunjungi Website", url="https://novus.web.id")]
        ])
    )

# --- CALLBACK UNTUK TOMBOL DONASI ---
@app.on_callback_query(filters.regex("start_donasi"))
async def donasi_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_states[user_id] = 1
    await callback_query.message.reply(
        "📸 **MODE DONASI AKTIF**\n\n"
        "Silakan kirimkan **Foto atau Video** Anda sekarang.\n"
        "Media akan otomatis diberi stiker Novus di posisi tengah."
    )
    await callback_query.answer()

# --- HANDLER PESAN MASUK ---
@app.on_message(filters.private & ~filters.command("start"))
async def handle_messages(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id, 0)

    # A. LOGIKA ADMIN BALAS MEMBER (Metode Reply)
    if user_id == DEVS and message.reply_to_message:
        try:
            # Mengambil ID dari teks info bot
            target_text = message.reply_to_message.text or message.reply_to_message.caption
            target_id = int(target_text.split("ID: `")[1].split("`")[0])
            
            await client.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]])
            )
            await message.reply_text(f"✅ Pesan terbalas ke `{target_id}`")
        except Exception:
            await message.reply_text("❌ Gagal balas: Reply pesan info ID dari bot.")
        return

    # B. LOGIKA MEMBER KIRIM MEDIA (MODE DONASI)
    if state == 1:
        if not (message.photo or message.video):
            await message.reply("⚠️ Mohon kirimkan Foto atau Video. Kirim pesan biasa untuk chat.")
            return

        status_msg = await message.reply("⏳ **Sedang memproses media...**")
        file_path = await message.download()
        output_path = f"novus_{os.path.basename(file_path)}"
        sticker_path = await client.download_media(STICKER_ID)

        try:
            # PROSES FOTO
            if message.photo:
                img = Image.open(file_path).convert("RGB")
                stk = Image.open(sticker_path).convert("RGBA")
                stk_w = img.width // 3
                w_percent = (stk_w / float(stk.size[0]))
                stk_h = int((float(stk.size[1]) * float(w_percent)))
                stk = stk.resize((stk_w, stk_h), Image.LANCZOS)
                pos = ((img.width - stk.width) // 2, (img.height - stk.height) // 2)
                img.paste(stk, pos, stk)
                img.save(output_path, "JPEG", quality=90)
                
                await client.send_photo(
                    DB_CHANNEL_ID, 
                    output_path, 
                    caption=f"📥 **DONASI FOTO**\n👤 User: `{user_id}`\n📝 Caption: {message.caption or '-'}"
                )

            # PROSES VIDEO
            elif message.video:
                clip = me.VideoFileClip(file_path)
                logo = (me.ImageClip(sticker_path)
                        .set_duration(clip.duration)
                        .resize(height=clip.h // 4)
                        .set_pos("center"))
                final = me.CompositeVideoClip([clip, logo])
                final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
                clip.close()
                
                await client.send_video(
                    DB_CHANNEL_ID, 
                    output_path, 
                    caption=f"📥 **DONASI VIDEO**\n👤 User: `{user_id}`\n📝 Caption: {message.caption or '-'}"
                )

            await message.reply("✅ **Terima kasih!** Donasi telah terkirim ke Database.")
            user_states[user_id] = 0 # Kembali ke mode chat biasa
            
        except Exception as e:
            logging.error(f"Error: {e}")
            await message.reply("❌ Gagal memproses media. Silakan coba lagi nanti.")
        finally:
            # Hapus file dari VPS (Cleanup)
            for f in [file_path, output_path, sticker_path]:
                if f and os.path.exists(f): os.remove(f)
            await status_msg.delete()
        return

    # C. LOGIKA MEMBER CHAT KE ADMIN (MODE CHAT)
    if user_id != DEVS:
        info_text = f"📩 **Pesan Baru**\n👤 Dari: {message.from_user.mention}\n🆔 ID: `{user_id}`\n\n👉 **Reply pesan ini untuk membalas.**"
        await message.forward(DEVS)
        await client.send_message(DEVS, info_text)

print("🚀 TestingNovusBot Berjalan!")
app.run()
