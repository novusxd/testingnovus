import os
import asyncio
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me
from motor.motor_asyncio import AsyncIOMotorClient

# Konfigurasi Logging
logging.basicConfig(level=logging.INFO)
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
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: Konfigurasi .env tidak valid! | {e}")
    exit()

# MongoDB Setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["NovusBotDB"]
users_col = db["nvs_users"]

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

forwarded_messages = {}
waiting_caption = {}

# --- FUNGSI DATABASE ---
async def add_user(user_id):
    await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)

async def remove_user(user_id):
    await users_col.delete_one({"_id": user_id})

async def get_all_users():
    return [doc["_id"] async for doc in users_col.find()]

# --- FUNGSI FIX PEER ID (SILENT PING) ---
async def fix_peer_id():
    """Memaksa bot mengenali ID Channel dengan mengirim pesan lalu menghapusnya."""
    print(f"🔄 Sinkronisasi ID Channel: {DB_CHANNEL}...")
    try:
        # Kirim pesan pancingan agar Bot mengenal ID ini
        pancing = await app.send_message(DB_CHANNEL, "🔄 *Bot System Synchronizing...*")
        await asyncio.sleep(1)
        await pancing.delete() # Hapus lagi agar channel tetap bersih
        print("✅ Sinkronisasi ID Berhasil! Bot sekarang mengenali Channel Database.")
    except Exception as e:
        print(f"❌ Gagal sinkronisasi: {e}")
        print("⚠️ Pastikan Bot sudah menjadi ADMIN di channel dan memiliki izin 'Post Messages'.")

# --- FUNGSI PROSES MEDIA ---
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

        await status.edit("✅ **Tersimpan di Database!**")
        info = await message_obj.forward(DEVS)
        forwarded_messages[info.id] = user_id
    except Exception as e:
        await status.edit(f"❌ Gagal: {e}")
    finally:
        for f in [file_p, out_p, stk_p]:
            if f and os.path.exists(f): os.remove(f)

# --- HANDLERS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id)
    await message.reply_text(f"👋 **Halo {message.from_user.first_name}!**\nKirim foto/video untuk donasi.")

@app.on_message(filters.command("stats") & filters.user(DEVS))
async def stats_cmd(client, message):
    count = await users_col.count_documents({})
    await message.reply_text(f"📊 **Statistik Database**\nTotal User (nvs): `{count}`")

@app.on_message(filters.command("broadcast") & filters.user(DEVS) & filters.reply)
async def broadcast_cmd(client, message):
    all_users = await get_all_users()
    msg = message.reply_to_message
    sent, failed = 0, 0
    status = await message.reply_text(f"🚀 **Broadcast sedang jalan...**")
    for u_id in all_users:
        try:
            await msg.copy(u_id)
            sent += 1
            await asyncio.sleep(0.3)
        except Exception:
            await remove_user(u_id)
            failed += 1
    await status.edit(f"✅ Selesai!\nBerhasil: `{sent}`\nGagal/Dihapus: `{failed}`")

@app.on_message(filters.private & ~filters.command(["start", "stats", "broadcast"]))
async def handle_msg(client, message):
    u_id = message.from_user.id
    await add_user(u_id)

    if u_id == DEVS and message.reply_to_message:
        target = forwarded_messages.get(message.reply_to_message.id)
        if target:
            try: await client.copy_message(target, message.chat.id, message.id)
            except: pass
        return

    if u_id in waiting_caption and message.text:
        media_msg = waiting_caption.pop(u_id)
        await process_media(client, u_id, media_msg, message.text)
        return

    if message.photo or message.video:
        if message.caption:
            await process_media(client, u_id, message, message.caption)
        else:
            waiting_caption[u_id] = message
            await message.reply_text("⚠️ **Berikan caption/deskripsi untuk media ini!**")
        return

    if u_id != DEVS:
        fw = await message.forward(DEVS)
        forwarded_messages[fw.id] = u_id
        await client.send_message(DEVS, f"📩 **Pesan dari {message.from_user.mention}**\nID: `{u_id}`")

# --- BOOTSTRAP ---
async def main():
    await app.start()
    await fix_peer_id() # Sinkronisasi ID via pesan pancingan
    print("🚀 Bot Novus Aktif & Database Sinkron!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
