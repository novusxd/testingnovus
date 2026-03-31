import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me

# Set up logging
logging.basicConfig(level=logging.INFO)

# Memuat file .env (Pastikan file bernama .env ada di folder yang sama)
load_dotenv()

# Konfigurasi dari Gist .env Anda
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID"))
except TypeError:
    print("❌ ERROR: File .env tidak ditemukan atau variabel kosong!")
    exit()

# ID STIKER UNTUK WATERMARK
STICKER_ID = "CAACAgUAAxkBAAEQ2Y9pzAOIPkrkqkB_qkpyqxt-qqoUSAAC_h4AApRBQVZfNG9E_iKx7DoE"

app = Client("NovusDonasiBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State user (0: Chat Biasa, 1: Mode Kirim Donasi)
user_states = {}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text(
        "👋 **Halo! Selamat datang di Novus Donasi.**\n\n"
        "Anda bisa mengobrol langsung dengan Admin di sini.\n"
        "Gunakan tombol di bawah jika ingin mengirim media donasi.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]])
    )

@app.on_callback_query(filters.regex("start_donasi"))
async def donasi_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_states[user_id] = 1
    await callback_query.message.reply("📸 **MODE DONASI AKTIF**\n\nSilakan kirimkan Foto atau Video Anda.\nMedia akan otomatis diberi watermark stiker Novus di tengah.")
    await callback_query.answer()

@app.on_message(filters.private & ~filters.command("start"))
async def handle_messages(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id, 0)

    # --- FITUR ADMIN BALAS MEMBER (Metode Reply) ---
    if user_id == DEVS and message.reply_to_message:
        try:
            # Mengambil ID dari teks info yang dikirim bot sebelumnya
            target_text = message.reply_to_message.text or message.reply_to_message.caption
            target_id = int(target_text.split("ID: `")[1].split("`")[0])
            
            await client.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Donasi Sekarang", callback_data="start_donasi")]])
            )
            await message.reply_text(f"✅ Terkirim ke member `{target_id}`")
        except Exception as e:
            await message.reply_text(f"❌ Gagal balas: Pastikan mereply pesan info dari bot.\nError: {e}")
        return

    # --- FITUR MEMBER KIRIM DONASI (STATE 1) ---
    if state == 1:
        if not (message.photo or message.video):
            await message.reply("⚠️ Mohon kirimkan Foto atau Video saja.")
            return

        status_msg = await message.reply("⏳ **Sedang memproses & menempel stiker...**")
        
        file_path = await message.download()
        output_path = f"novus_{os.path.basename(file_path)}"
        sticker_path = await client.download_media(STICKER_ID)

        try:
            # JIKA MEDIA ADALAH FOTO
            if message.photo:
                img = Image.open(file_path).convert("RGB")
                stk = Image.open(sticker_path).convert("RGBA")
                
                # Resize stiker otomatis (1/3 lebar foto)
                stk_w = img.width // 3
                w_percent = (stk_w / float(stk.size[0]))
                stk_h = int((float(stk.size[1]) * float(w_percent)))
                stk = stk.resize((stk_w, stk_h), Image.LANCZOS)
                
                # Tempel di tengah
                pos = ((img.width - stk.width) // 2, (img.height - stk.height) // 2)
                img.paste(stk, pos, stk)
                img.save(output_path, "JPEG", quality=90)
                
                await client.send_photo(
                    DB_CHANNEL_ID, 
                    output_path, 
                    caption=f"📥 **DONASI FOTO**\n👤 User: `{user_id}`\n📝 Caption: {message.caption or '-'}"
                )

            # JIKA MEDIA ADALAH VIDEO
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

            await message.reply("✅ **Selesai!** Donasi telah masuk ke Database.")
            user_states[user_id] = 0 # Kembali ke mode chat
            
        except Exception as e:
            logging.error(e)
            await message.reply("❌ Gagal memproses media.")
        finally:
            # HAPUS FILE DARI VPS (CLEANUP)
            for f in [file_path, output_path, sticker_path]:
                if f and os.path.exists(f):
                    os.remove(f)
            await status_msg.delete()
        return

    # --- FITUR MEMBER CHAT KE ADMIN (STATE 0) ---
    if user_id != DEVS:
        user_info = f"📩 **Pesan Baru**\n👤 Dari: {message.from_user.mention}\n🆔 ID: `{user_id}`\n\n👉 **Reply pesan ini untuk membalas.**"
        await message.forward(DEVS)
        await client.send_message(DEVS, user_info)

print("🚀 Novus Donasi Bot AKTIF!")
app.run()
