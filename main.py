import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me

# Logging untuk memantau aktivitas bot
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Konfigurasi dari .env
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEVS = int(os.getenv("DEVS"))
DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID"))
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("NovusDonasiBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State user (0: Chat, 1: Menunggu Media Donasi)
user_states = {}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text(
        "👋 **Halo! Selamat datang di Layanan Donasi Novus.**\n\n"
        "Silakan kirim pesan di sini untuk mengobrol dengan Admin.\n"
        "Jika ingin membantu meramaikan channel, klik tombol **Donasi Sekarang** di bawah balasan Admin nanti.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]])
    )

@app.on_callback_query(filters.regex("start_donasi"))
async def donasi_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_states[user_id] = 1
    await callback_query.message.reply("📸 **Mode Donasi Aktif!**\n\nSilakan kirimkan **Foto atau Video** beserta captionnya. Media Anda akan otomatis diberi watermark stiker Novus.")
    await callback_query.answer()

@app.on_message(filters.private & ~filters.command("start"))
async def handle_messages(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id, 0)

    # --- LOGIKA ADMIN BALAS MEMBER ---
    if user_id == DEVS and message.reply_to_message:
        # Mencari ID target dari teks info yang dikirim bot sebelumnya
        try:
            target_text = message.reply_to_message.text or message.reply_to_message.caption
            target_id = int(target_text.split("ID: `")[1].split("`")[0])
            
            await client.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]])
            )
            await message.reply_text(f"✅ Pesan terbalas ke `{target_id}`")
        except Exception as e:
            await message.reply_text(f"❌ Gagal membalas: ID tidak ditemukan atau user memblokir bot.\nError: {e}")
        return

    # --- LOGIKA MEMBER KIRIM MEDIA DONASI (STATE 1) ---
    if state == 1:
        if not (message.photo or message.video):
            await message.reply("⚠️ Mohon kirimkan **Foto atau Video**. Gunakan tombol 'Donasi Sekarang' lagi jika ingin membatalkan.")
            return

        status_msg = await message.reply("⏳ **Sedang memproses media... Mohon tunggu.**")
        
        file_path = await message.download()
        output_path = f"novus_{os.path.basename(file_path)}"
        sticker_path = await client.download_media(STICKER_ID)

        try:
            # PROSES FOTO
            if message.photo:
                img = Image.open(file_path).convert("RGB")
                stk = Image.open(sticker_path).convert("RGBA")
                
                # Resize stiker (30% dari lebar foto)
                base_w = img.width // 3
                w_percent = (base_w / float(stk.size[0]))
                h_size = int((float(stk.size[1]) * float(w_percent)))
                stk = stk.resize((base_w, h_size), Image.LANCZOS)
                
                # Paste di tengah
                pos = ((img.width - stk.width) // 2, (img.height - stk.height) // 2)
                img.paste(stk, pos, stk)
                img.save(output_path, "JPEG", quality=95)
                
                await client.send_photo(
                    DB_CHANNEL_ID, 
                    output_path, 
                    caption=f"📥 **Donasi Baru**\n👤 Dari: `{user_id}`\n📝 Caption: {message.caption or 'Tanpa keterangan'}"
                )

            # PROSES VIDEO
            elif message.video:
                video = me.VideoFileClip(file_path)
                logo = (me.ImageClip(sticker_path)
                        .set_duration(video.duration)
                        .resize(height=video.h // 4)
                        .set_pos("center"))
                
                final = me.CompositeVideoClip([video, logo])
                final.write_videofile(output_path, codec="libx264", audio_codec="aac")
                video.close() # Penting agar file bisa dihapus
                
                await client.send_video(
                    DB_CHANNEL_ID, 
                    output_path, 
                    caption=f"📥 **Donasi Baru**\n👤 Dari: `{user_id}`\n📝 Caption: {message.caption or 'Tanpa keterangan'}"
                )

            await message.reply("✅ **Sukses!** Media Anda telah dikirim ke Database.")
            user_states[user_id] = 0 # Reset ke mode chat biasa
            
        except Exception as e:
            logging.error(f"Error Processing: {e}")
            await message.reply(f"❌ Terjadi kesalahan saat memproses media.")
        finally:
            # Hapus file sampah di VPS
            for f in [file_path, output_path, sticker_path]:
                if f and os.path.exists(f):
                    os.remove(f)
            await status_msg.delete()
        return

    # --- LOGIKA MEMBER CHAT KE ADMIN (STATE 0) ---
    if user_id != DEVS:
        info_text = f"📩 **Pesan Baru**\n👤 Dari: {message.from_user.mention}\n🆔 ID: `{user_id}`\n\n👇 Balas pesan ini untuk menjawab."
        await message.forward(DEVS)
        await client.send_message(DEVS, info_text)

print("🚀 Novus Donasi Bot sedang berjalan...")
app.run()
