import os
import shutil
import asyncio
import patoolib
import aiohttp
import mimetypes
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

# --- Config (GitHub Secrets) ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BUNNY_STORAGE_KEY = os.getenv("BUNNY_STORAGE_KEY")
BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE")
BUNNY_STREAM_KEY = os.getenv("BUNNY_STREAM_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")

mimetypes.init()

# Global setup
app = Client("bunny_bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
queue = None

# --- Helper Functions (Storage & Stream) ---

async def upload_to_storage(local_path, bunny_path):
    url = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}/{bunny_path}"
    headers = {"AccessKey": BUNNY_STORAGE_KEY, "Content-Type": "application/octet-stream"}
    async with aiohttp.ClientSession() as session:
        with open(local_path, 'rb') as f:
            await session.put(url, headers=headers, data=f)

async def upload_to_stream(local_path, video_name):
    headers = {"AccessKey": BUNNY_STREAM_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        create_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
        async with session.post(create_url, headers=headers, json={'title': video_name}) as r:
            res = await r.json()
            video_id = res['guid']
        upload_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video_id}"
        with open(local_path, 'rb') as f:
            await session.put(upload_url, headers=headers, data=f)

def is_archive(file_path):
    return file_path.lower().endswith(('.zip', '.rar', '.7z', '.tar', '.gz'))

def is_video(file_path):
    mime, _ = mimetypes.guess_type(file_path)
    return (mime and mime.startswith('video/')) or file_path.lower().endswith(('.mp4', '.mkv', '.mov', '.webm', '.flv', '.avi', '.ts'))

async def recursive_process(path, status_msg):
    if is_archive(path):
        extract_dir = f"{path}_extracted"
        os.makedirs(extract_dir, exist_ok=True)
        await status_msg.edit_text(f"📦 Extracting: {os.path.basename(path)}")
        try:
            patoolib.extract_archive(path, outdir=extract_dir, verbosity=-1)
            if os.path.exists(path): os.remove(path)
            for root, _, files in os.walk(extract_dir):
                for f in files:
                    await recursive_process(os.path.join(root, f), status_msg)
        except Exception as e:
            print(f"Extraction error: {e}")
        if os.path.exists(extract_dir): shutil.rmtree(extract_dir)
    elif is_video(path):
        await status_msg.edit_text(f"🎬 Streaming: {os.path.basename(path)}")
        await upload_to_stream(path, os.path.basename(path))
        if os.path.exists(path): os.remove(path)
    else:
        await status_msg.edit_text(f"📁 Storing: {os.path.basename(path)}")
        await upload_to_storage(path, os.path.basename(path))
        if os.path.exists(path): os.remove(path)

# --- Worker & Handler ---

async def worker():
    while True:
        message = await queue.get()
        try:
            status = await message.reply_text("⏳ Processing starting...")
            file_path = await message.download()
            await recursive_process(file_path, status)
            await status.edit_text("✅ All done!")
        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            queue.task_done()

@app.on_message(filters.chat("me") & filters.document)
async def producer(client, message):
    await queue.put(message)

# --- Main Boot ---

async def main():
    global queue
    queue = asyncio.Queue()
    
    # Start the client
    await app.start()
    
    # CRITICAL: Force the session to recognize 'me' and Saved Messages
    try:
        me = await app.get_me()
        print(f"Logged in as: {me.first_name}")
        await app.send_message("me", "🚀 Userbot active and watching Saved Messages.")
    except Exception as e:
        print(f"Initial sync error: {e}")

    # Start worker
    asyncio.create_task(worker())
    print("Bot is fully initialized. Send a file to Saved Messages.")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Suppress the update errors that don't affect our specific chat
    import logging
    logging.getLogger("pyrogram").setLevel(logging.ERROR)
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
