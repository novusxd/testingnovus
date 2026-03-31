import os
import asyncio
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError

# Konfigurasi Logging agar muncul di terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("NovusBot")

load_dotenv()

# Ambil data dari .env
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL = int(os.getenv("DB_CHANNEL"))
    STICKER_ID = os.getenv("STICKER_ID")
    MONGO_URL = os.getenv("MONGO_URL")
except Exception as e:
    logger.error(f"Gagal memuat .env: {e}")
    exit()

# MongoDB Setup dengan Timeout 5 detik agar tidak hang
mongo_client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = mongo_client["NovusBotDB"]
users_col = db["nvs_users"]
config_col = db["nvs_config"]

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

forwarded_messages = {}
waiting_caption = {}

# --- FUNGSI DATABASE ---
async def add_user(user_id):
    try:
        await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)
    except Exception as e:
        logger.error(f"Gagal simpan user ke DB: {e}")

async def ensure_channel_verified():
    logger.info(f"🔍 Mengecek verifikasi channel {DB_CHANNEL}...")
    try:
        # Cek status di MongoDB
        check = await config_col.find_one({"_id": "channel_verification"})
        if check and check.get("verified"):
            logger.info("✅ Channel sudah terverifikasi sebelumnya.")
            return

        # Silent Ping jika belum verified
        logger.info("🔄 Melakukan Silent Ping ke Channel...")
        pancing = await app.send_message(DB_CHANNEL, "🔄 **System Sync...**")
        await asyncio.sleep(1)
        await pancing.delete()
        
        await config_col.update_one(
            {"_id": "channel_verification"}, 
            {"$set": {"verified": True}}, 
            upsert=True
        )
        logger.info("✅ Verifikasi Berhasil Simpan ke DB.")
    except ServerSelectionTimeoutError:
        logger.error("❌ KONEKSI MONGO TIMEOUT! Pastikan IP VPS sudah di-whitelist di MongoDB Atlas.")
    except Exception as e:
        logger.error(f"❌ Gagal verifikasi channel: {e}")

# --- FUNGSI MEDIA ---
async def process_media(client, user_id, message_obj, caption_text):
    status = await client.send_message(user_id, "⏳ **Memproses watermark...**")
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
            await client.send_photo(DB_CHANNEL, out_p, caption=caption_text)
        elif message_obj.video:
            clip = me.VideoFileClip(file_p)
            logo = (me.ImageClip(stk_p).set_duration(clip.duration).resize(height=clip.h // 4).set_pos("center"))
            final = me.CompositeVideoClip([clip, logo])
            final.write_videofile(out_p, codec="libx264", audio_codec="aac", logger=None)
            clip.close()
            await client.send_video(DB_CHANNEL, out_p, caption=caption_text)

        await status.edit("✅ **Berhasil terkirim ke Database.**")
        info = await message_obj.forward(DEVS)
        forwarded_messages[info.id] = user_id
    except Exception as e:
        await status.edit(f"❌ Terjadi kesalahan: {e}")
    finally:
        for f in [file_p, out_p, stk_p]:
            if f and os.path.exists(f): os.remove(f)

# --- HANDLERS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    logger.info(f"Pesan /start dari {message.from_user.id}")
    await add_user(message.from_user.id)
    await message.reply_text(f"👋 **Halo {message.from_user.first_name}!**\nBot sudah aktif. Silakan kirim media.")

@app.on_message(filters.command("stats") & filters.user(DEVS))
async def stats_cmd(client, message):
    count = await users_col.count_documents({})
    await message.reply_text(f"📊 Total User: `{count}`")

@app.on_message(filters.private & ~filters.command(["start", "stats"]))
async def handle_msg(client, message):
    u_id = message.from_user.id
    await add_user(u_id)

    # Admin Reply
    if u_id == DEVS and message.reply_to_message:
        target = forwarded_messages.get(message.reply_to_message.id)
        if target:
            try: await client.copy_message(target, message.chat.id, message.id)
            except: pass
        return

    # Waiting Caption
    if u_id in waiting_caption and message.text:
        media_msg = waiting_caption.pop(u_id)
        await process_media(client, u_id, media_msg, message.text)
        return

    # Media Check
    if message.photo or message.video:
        if message.caption:
            await process_media(client, u_id, message, message.caption)
        else:
            waiting_caption[u_id] = message
            await message.reply_text("⚠️ **Silakan kirim caption/deskripsi!**")
        return

    # Forward to Admin
    if u_id != DEVS:
        fw = await message.forward(DEVS)
        forwarded_messages[fw.id] = u_id
        await client.send_message(DEVS, f"📩 Pesan dari `{u_id}`")

# --- MAIN ---
async def main():
    logger.info("🚀 Memulai Bot...")
    await app.start()
    
    # Cek Koneksi DB & Verifikasi Channel
    try:
        await ensure_channel_verified()
    except Exception as e:
        logger.error(f"Gagal verifikasi saat startup: {e}")

    logger.info("✅ Bot Novus Ready!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan.")
