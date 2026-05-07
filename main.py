import os, shutil, asyncio, patoolib, aiohttp, mimetypes, time
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# --- Config ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BUNNY_STORAGE_KEY = os.getenv("BUNNY_STORAGE_KEY")
BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE")
BUNNY_STREAM_KEY = os.getenv("BUNNY_STREAM_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")

mimetypes.init()
app = Client("bunny_bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
queue = None

# --- Progress Tracker ---
async def progress(current, total, status_msg, action):
    now = time.time()
    if not hasattr(progress, "last"): progress.last = 0
    if now - progress.last > 20:
        perc = (current * 100 / total) if total > 0 else 0
        try:
            await status_msg.edit_text(f"⏳ **{action}**\n📊 Progress: `{perc:.1f}%`\n📦 Size: `{current // 1024 // 1024}MB / {total // 1024 // 1024}MB`")
        except FloodWait as e:
            await asyncio.sleep(e.value)
        progress.last = now

# --- Enhanced Storage Upload ---
async def upload_to_storage(local_path, bunny_path, status):
    url = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}/{bunny_path}"
    headers = {"AccessKey": BUNNY_STORAGE_KEY}
    file_size = os.path.getsize(local_path) // 1024
    
    await status.edit_text(f"🚀 **Uploading to Storage**\n📄 File: `{bunny_path}`\n⚖️ Size: `{file_size}KB`")
    
    async with aiohttp.ClientSession() as session:
        try:
            with open(local_path, 'rb') as f:
                async with session.put(url, headers=headers, data=f) as r:
                    if r.status in [200, 201]:
                        print(f"✅ Successfully stored: {bunny_path}")
                    else:
                        resp_text = await r.text()
                        await status.reply_text(f"❌ **Storage Error ({r.status})**\nTarget: `{bunny_path}`\nResponse: `{resp_text}`")
        except Exception as e:
            await status.reply_text(f"⚠️ **Storage Exception:** `{str(e)}`")

# --- Enhanced Stream Upload ---
async def upload_to_stream(local_path, name, status):
    headers = {"AccessKey": BUNNY_STREAM_KEY, "Content-Type": "application/json"}
    await status.edit_text(f"🎬 **Creating Stream Entry**\n🎥 Video: `{name}`")
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. Create entry
            c_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
            async with session.post(c_url, headers=headers, json={'title': name}) as r:
                if r.status != 200:
                    await status.reply_text(f"❌ **Stream API Error ({r.status})**\nCould not create video entry.")
                    return
                vid_id = (await r.json())['guid']

            # 2. Upload
            await status.edit_text(f"📡 **Streaming Binary to Bunny**\n🆔 ID: `{vid_id}`\n🎥 Video: `{name}`")
            u_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{vid_id}"
            with open(local_path, 'rb') as f:
                async with session.put(u_url, headers=headers, data=f) as r:
                    if r.status not in [200, 201]:
                        await status.reply_text(f"❌ **Stream Upload Error ({r.status})**")
        except Exception as e:
            await status.reply_text(f"⚠️ **Stream Exception:** `{str(e)}`")

# --- Recursive Process ---
async def recursive_process(path, status):
    file_name = os.path.basename(path)
    
    if path.lower().endswith(('.zip', '.rar', '.7z', '.tar', '.gz')):
        ex_dir = f"{path}_ex"
        os.makedirs(ex_dir, exist_ok=True)
        await status.edit_text(f"📦 **Extracting Archive**\n📂 `{file_name}`")
        
        try:
            patoolib.extract_archive(path, outdir=ex_dir, verbosity=-1)
            if os.path.exists(path): os.remove(path)
            
            for root, _, files in os.walk(ex_dir):
                for f in files:
                    await recursive_process(os.path.join(root, f), status)
        except Exception as e:
            await status.reply_text(f"❌ **Extraction Failed**\nFile: `{file_name}`\nError: `{str(e)}`")
        
        if os.path.exists(ex_dir): shutil.rmtree(ex_dir)

    elif mimetypes.guess_type(path)[0] and 'video' in mimetypes.guess_type(path)[0]:
        await upload_to_stream(path, file_name, status)
        if os.path.exists(path): os.remove(path)
    else:
        await upload_to_storage(path, file_name, status)
        if os.path.exists(path): os.remove(path)

# --- Worker Logic ---
async def worker():
    while True:
        msg = await queue.get()
        status = await msg.reply_text("🛰️ **Server-side Task Received**\nPreparing to download...")
        try:
            path = await msg.download(progress=progress, progress_args=(status, "Downloading from Telegram"))
            await recursive_process(path, status)
            await status.edit_text("🎯 **Mission Accomplished**\nAll files processed and uploaded to Bunny.net.")
        except Exception as e:
            await status.edit_text(f"🚨 **Worker Crash**\n`{str(e)}`")
        finally:
            queue.task_done()

@app.on_message(filters.chat("me") & filters.document)
async def producer(_, msg):
    await queue.put(msg)
    # Give instant feedback to show the bot isn't stuck
    await msg.reply_text("📝 **File Added to Queue**\nWait for the worker to start...")

async def main():
    global queue
    queue = asyncio.Queue()
    await app.start()
    await app.send_message("me", "⚡ **Cloud Automation Online**\nForward any archive or video here.")
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
