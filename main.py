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

# Konfigurasi
try:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVS = int(os.getenv("DEVS"))
    DB_CHANNEL = int(os.getenv("DB_CHANNEL"))
    STICKER_ID = os.getenv("STICKER_ID")
    MONGO_URL = os.getenv("MONGO_URL")
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: Pastikan .env lengkap! | {e}")
    exit()

# MongoDB Setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["NovusBotDB"]
users_col = db["nvs_users"]

app = Client("TestingNovusBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Memori Internal
forwarded_messages = {}
waiting_caption = {}

# --- FUNGSI DATABASE ---
async def add_user(user_id):
    await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)

async def remove_user(user_id):
    await users_col.delete_one({"_id": user_id})

async def get_all_users():
    return [doc["_id"] async for doc in users_col.find()]

# --- FUNGSI AUTO-RESOLVE CHANNEL ---
async def resolve_database_channel():
    """Memaksa bot mengenali channel database saat startup."""
    try:
        chat = await app.get_chat(DB_CHANNEL)
        print(f"✅ Berhasil mengenali Channel: {chat.title} ({DB_CHANNEL})")
    except Exception as e:
        print(f"⚠️ PERINGATAN: Bot belum bisa mengenali channel {DB_CHANNEL}.")
        print(f"Pastikan bot sudah menjadi ADMIN di channel tersebut! Error: {e}")

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
        
        info = await message_obj.forward(DEVS)
        forwarded_messages[info.id] = user_id
        await client.send_message(DEVS, f"📥 **Donasi Baru (nvs)**\n👤 User: {message_obj.from_user.mention}\n🆔 ID: `{user_id}`")

    except Exception as e:
        logging.error(e)
        await status.edit(f"❌ Gagal memproses: {e}")
    finally:
        for f in [file_p, out_p, stk_p]:
            if f and os.path.exists(f): os.remove(f)

# --- HANDLER ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id)
    await message.reply_text(f"👋 **Halo {message.from_user.first_name}!**\nKirim foto/video untuk donasi.")

@app.on_message(filters.command("stats") & filters.user(DEVS))
async def stats_cmd(client, message):
    count = await users_col.count_documents({})
    await message.reply_text(f"📊 **Statistik Database (nvs_users)**\nTotal User: `{count}`")

@app.on_message(filters.command("broadcast") & filters.user(DEVS) & filters.reply)
async def broadcast_cmd(client, message):
    all_users = await get_all_users()
    msg_to_broadcast = message.reply_to_message
    sent, failed = 0, 0
    status = await message.reply_text(f"🚀 **Broadcast dimulai...**")

    for user_id in all_users:
        try:
            await msg_to_broadcast.copy(user_id)
            sent += 1
            await asyncio.sleep(0.3)
        except (errors.UserIsBlocked, errors.PeerIdInvalid, errors.InputUserDeactivated):
            await remove_user(user_id)
            failed += 1
        except Exception:
            failed += 1

    await status.edit(f"✅ **Selesai!**\nBerhasil: `{sent}`\nGagal: `{failed}`")

@app.on_message(filters.private & ~filters.command(["start", "stats", "broadcast"]))
async def handle_everything(client, message):
    user_id = message.from_user.id
    await add_user(user_id)

    if user_id == DEVS and message.reply_to_message:
        target_id = forwarded_messages.get(message.reply_to_message.id)
        if target_id:
            try:
                await client.copy_message(target_id, message.chat.id, message.id)
                await message.reply_text("✅ Terbalas.")
            except: pass
        return

    if user_id in waiting_caption and message.text:
        media_msg = waiting_caption.pop(user_id)
        await process_and_send(client, user_id, media_msg, message.text)
        return

    if message.photo or message.video:
        if message.caption:
            await process_and_send(client, user_id, message, message.caption)
        else:
            waiting_caption[user_id] = message
            await message.reply_text("⚠️ **Kirimkan caption untuk media ini!**")
        return

    if user_id != DEVS:
        fw = await message.forward(DEVS)
        forwarded_messages[fw.id] = user_id
        await client.send_message(DEVS, f"📩 **Pesan dari {message.from_user.mention}**\nID: `{user_id}`")

# --- BOOTSTRAP ---
async def main():
    await app.start()
    await resolve_database_channel() # Langkah Kunci: Kenali Channel Database
    print("🚀 Bot Novus Aktif & Siap!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
