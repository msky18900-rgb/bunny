import os, shutil, asyncio, patoolib, aiohttp, mimetypes, time, logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# Suppress background "Peer ID" noise
logging.getLogger("pyrogram").setLevel(logging.ERROR)

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
queue = asyncio.Queue()

# --- Helpers ---
async def progress(current, total, status_msg, action):
    now = time.time()
    if not hasattr(progress, "last"): progress.last = 0
    if now - progress.last > 20:
        perc = (current * 100 / total) if total > 0 else 0
        try: await status_msg.edit_text(f"⏳ **{action}**\n📊 `{perc:.1f}%`")
        except: pass
        progress.last = now

async def upload_to_storage(local_path, bunny_path, status):
    url = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}/{bunny_path}"
    headers = {"AccessKey": BUNNY_STORAGE_KEY}
    async with aiohttp.ClientSession() as session:
        with open(local_path, 'rb') as f:
            async with session.put(url, headers=headers, data=f) as r:
                if r.status not in [200, 201]:
                    await status.reply_text(f"❌ Storage Error {r.status}")

async def upload_to_stream(local_path, name, status):
    headers = {"AccessKey": BUNNY_STREAM_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        c_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
        async with session.post(c_url, headers=headers, json={'title': name}) as r:
            vid_id = (await r.json())['guid']
        u_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{vid_id}"
        with open(local_path, 'rb') as f:
            await session.put(u_url, headers=headers, data=f)

async def recursive_process(path, status):
    file_name = os.path.basename(path)
    if path.lower().endswith(('.zip', '.rar', '.7z', '.tar', '.gz')):
        ex_dir = f"{path}_ex"
        os.makedirs(ex_dir, exist_ok=True)
        await status.edit_text(f"📦 Extracting: `{file_name}`")
        try:
            patoolib.extract_archive(path, outdir=ex_dir, verbosity=-1)
            if os.path.exists(path): os.remove(path)
            for root, _, files in os.walk(ex_dir):
                for f in files:
                    await recursive_process(os.path.join(root, f), status)
        finally:
            if os.path.exists(ex_dir): shutil.rmtree(ex_dir)
    elif mimetypes.guess_type(path)[0] and 'video' in mimetypes.guess_type(path)[0]:
        await status.edit_text(f"🎬 Streaming: `{file_name}`")
        await upload_to_stream(path, file_name, status)
        if os.path.exists(path): os.remove(path)
    else:
        await status.edit_text(f"📁 Storing: `{file_name}`")
        await upload_to_storage(path, file_name, status)
        if os.path.exists(path): os.remove(path)

# --- Worker ---
async def worker():
    while True:
        msg = await queue.get()
        shutil.rmtree("downloads", ignore_errors=True)
        status = await msg.reply_text("🚀 **Processing Started...**")
        try:
            path = await msg.download(progress=progress, progress_args=(status, "Downloading from TG"))
            await recursive_process(path, status)
            await status.edit_text("🎯 **Complete. Disk Wiped.**")
        except Exception as e:
            await status.edit_text(f"🚨 **Error:** `{str(e)}`")
        finally:
            queue.task_done()

# --- Broad Listener ---
# This will catch everything (new or forwarded) in your Saved Messages
@app.on_message(filters.chat("me") & (filters.document | filters.video))
async def producer(_, msg):
    await queue.put(msg)
    await msg.reply_text("✅ **Added to Queue**")

async def main():
    await app.start()
    # Force self-recognition
    me = await app.get_me()
    await app.send_message("me", f"⚡ **Bot Online for {me.first_name}**\nForward files here now.")
    
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
