import os
import asyncio
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from PIL import Image
import moviepy.editor as me
from motor.motor_asyncio import AsyncIOMotorClient

# Logging
logging.basicConfig(level=logging.INFO)
load_dotenv()

# Konfigurasi dari Gist Terbaru
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL = int(os.getenv("DB_CHANNEL"))
    STICKER_ID = os.getenv("STICKER_ID")
    MONGO_URL = os.getenv("MONGO_URL")
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: Pastikan semua variabel di .env sudah terisi! | {e}")
    exit()

# MongoDB Setup dengan Prefix "nvs"
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["NovusBotDB"]
users_col = db["nvs_users"] # Koleksi menggunakan prefix nvs

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Memori Internal
forwarded_messages = {}
waiting_caption = {}

# --- FUNGSI DATABASE ---
async def add_user(user_id):
    """Menambah user ke koleksi nvs_users."""
    await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)

async def remove_user(user_id):
    """Menghapus user (Auto-Cleanup)."""
    await users_col.delete_one({"_id": user_id})

async def get_all_users():
    """Mengambil semua ID user untuk broadcast."""
    return [doc["_id"] async for doc in users_col.find()]

# --- FUNGSI PROSES MEDIA ---
async def process_and_send(client, user_id, message_obj, caption_text):
    status = await client.send_message(user_id, "⏳ **Sedang memproses watermark...**")
    
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
            await client.send_photo(chat_id=DB_CHANNEL, photo=out_p, caption=caption_text)

        elif message_obj.video:
            clip = me.VideoFileClip(file_p)
            logo = (me.ImageClip(stk_p).set_duration(clip.duration).resize(height=clip.h // 4).set_pos("center"))
            final = me.CompositeVideoClip([clip, logo])
            final.write_videofile(out_p, codec="libx264", audio_codec="aac", logger=None)
            clip.close()
            await client.send_video(chat_id=DB_CHANNEL, video=out_p, caption=caption_text)

        await status.edit("✅ **Berhasil!** Media terkirim ke database.")
        
        # Laporan ke Admin
        info = await message_obj.forward(DEVS)
        forwarded_messages[info.id] = user_id
        await client.send_message(DEVS, f"📥 **Donasi Baru (Prefix: nvs)**\n👤 User: {message_obj.from_user.mention}\n🆔 ID: `{user_id}`")

    except Exception as e:
        logging.error(e)
        await status.edit(f"❌ Gagal memproses: {e}")
    finally:
        for f in [file_p, out_p, stk_p]:
            if f and os.path.exists(f): os.remove(f)

# --- HANDLER UTAMA ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id)
    await message.reply_text(
        f"👋 **Halo {message.from_user.first_name}!**\n\n"
        "Selamat datang di **Testing Novus Bot**.\n"
        "Kirim foto atau video untuk donasi. Bot akan otomatis meminta caption jika kosong."
    )

@app.on_message(filters.command("stats") & filters.user(DEVS))
async def stats_cmd(client, message):
    count = await users_col.count_documents({})
    await message.reply_text(f"📊 **Statistik Database (nvs_users)**\nTotal User: `{count}`")

@app.on_message(filters.command("broadcast") & filters.user(DEVS) & filters.reply)
async def broadcast_cmd(client, message):
    all_users = await get_all_users()
    msg_to_broadcast = message.reply_to_message
    sent, failed = 0, 0
    status = await message.reply_text(f"🚀 **Broadcast dimulai...**\nTarget: {len(all_users)} user.")

    for user_id in all_users:
        try:
            await msg_to_broadcast.copy(user_id)
            sent += 1
            await asyncio.sleep(0.3)
        except (errors.UserIsBlocked, errors.PeerIdInvalid, errors.InputUserDeactivated):
            await remove_user(user_id) # Hapus user yang sudah tidak aktif
            failed += 1
        except Exception:
            failed += 1

    await status.edit(f"✅ **Broadcast Selesai!**\n\nBerhasil: `{sent}`\nGagal/Dihapus: `{failed}`")

@app.on_message(filters.private & ~filters.command(["start", "stats", "broadcast"]))
async def handle_everything(client, message):
    user_id = message.from_user.id
    await add_user(user_id) # Simpan setiap user baru

    # 1. Balas Member oleh Admin
    if user_id == DEVS and message.reply_to_message:
        target_id = forwarded_messages.get(message.reply_to_message.id)
        if target_id:
            try:
                await client.copy_message(target_id, message.chat.id, message.id)
                await message.reply_text("✅ Terbalas.")
            except: pass
        return

    # 2. Menunggu Caption Media
    if user_id in waiting_caption and message.text:
        media_msg = waiting_caption.pop(user_id)
        await process_and_send(client, user_id, media_msg, message.text)
        return

    # 3. Kirim Media
    if message.photo or message.video:
        if message.caption:
            await process_and_send(client, user_id, message, message.caption)
        else:
            waiting_caption[user_id] = message
            await message.reply_text("⚠️ **Kirimkan caption untuk media ini!**")
        return

    # 4. Chat Biasa
    if user_id != DEVS:
        fw = await message.forward(DEVS)
        forwarded_messages[fw.id] = user_id
        await client.send_message(DEVS, f"📩 **Pesan dari {message.from_user.mention}**\nID: `{user_id}`")

print("🚀 Bot Novus Berjalan! Koleksi: nvs_users")
app.run()
