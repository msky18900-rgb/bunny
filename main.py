import os
import shutil
import asyncio
import patoolib
import aiohttp
import mimetypes
from pyrogram import Client, filters

# --- Config (GitHub Secrets) ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BUNNY_STORAGE_KEY = os.getenv("BUNNY_STORAGE_KEY")
BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE")
BUNNY_STREAM_KEY = os.getenv("BUNNY_STREAM_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")

mimetypes.init()
app = Client("bunny_bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
queue = asyncio.Queue()

# --- Helper Functions ---

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
        await status_msg.edit_text(f"📦 Extracting Archive: {os.path.basename(path)}")
        
        try:
            patoolib.extract_archive(path, outdir=extract_dir, verbosity=-1)
            if os.path.exists(path): os.remove(path)

            for root, _, files in os.walk(extract_dir):
                for f in files:
                    file_full_path = os.path.join(root, f)
                    await recursive_process(file_full_path, status_msg)
        except Exception as e:
            print(f"Extraction error: {e}")
        
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

    elif is_video(path):
        await status_msg.edit_text(f"🎬 [STREAM] Uploading: {os.path.basename(path)}")
        await upload_to_stream(path, os.path.basename(path))
        if os.path.exists(path): os.remove(path)
    
    else:
        await status_msg.edit_text(f"📁 [STORAGE] Uploading: {os.path.basename(path)}")
        bunny_path = os.path.basename(path)
        await upload_to_storage(path, bunny_path)
        if os.path.exists(path): os.remove(path)

# --- Queue Worker ---

async def worker():
    while True:
        message = await queue.get()
        try:
            status = await message.edit_text("⏳ Download starting...")
            file_path = await message.download()
            await recursive_process(file_path, status)
            await status.edit_text("✅ All contents processed and uploaded!")
        except Exception as e:
            await message.reply_text(f"❌ Critical Error: {str(e)}")
        finally:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            queue.task_done()

@app.on_message(filters.me & filters.document)
async def producer(client, message):
    await queue.put(message)
    await message.edit_text("📝 Added to Queue. Moving to server-side processing...")

# --- Boot ---

async def main():
    await app.start()
    print("Userbot Online.")
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
