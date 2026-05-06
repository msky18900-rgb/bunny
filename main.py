import os
import zipfile
import shutil
import aiohttp
import asyncio
from pyrogram import Client, filters

# Environment Variables from GitHub Secrets
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BUNNY_STORAGE_KEY = os.getenv("BUNNY_STORAGE_KEY")
BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE")
BUNNY_STREAM_KEY = os.getenv("BUNNY_STREAM_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

async def upload_to_storage(local_path, bunny_path):
    url = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE}/{bunny_path}"
    headers = {"AccessKey": BUNNY_STORAGE_KEY, "Content-Type": "application/octet-stream"}
    async with aiohttp.ClientSession() as session:
        with open(local_path, 'rb') as f:
            await session.put(url, headers=headers, data=f)

async def upload_to_stream(local_path, video_name):
    headers = {"AccessKey": BUNNY_STREAM_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        # Create video entry
        create_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
        async with session.post(create_url, headers=headers, json={'title': video_name}) as r:
            video_id = (await r.json())['guid']
        
        # Upload binary
        upload_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video_id}"
        with open(local_path, 'rb') as f:
            await session.put(upload_url, headers=headers, data=f)
    return video_id

@app.on_message(filters.me & filters.document)
async def handle_files(client, message):
    file_name = message.document.file_name
    status = await message.edit_text(f"📥 Downloading {file_name} to Cloud...")
    path = await message.download()

    if file_name.lower().endswith(".zip"):
        await status.edit_text("📦 Extracting ZIP server-side...")
        extract_dir = f"extracted_{message.id}"
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        await status.edit_text("🚀 Pushing files to Bunny Storage...")
        for root, _, files in os.walk(extract_dir):
            for f in files:
                local_file = os.path.join(root, f)
                rel_path = os.path.relpath(local_file, extract_dir)
                await upload_to_storage(local_file, rel_path)
        shutil.rmtree(extract_dir)
        await status.edit_text("✅ ZIP opened & uploaded to Storage!")

    elif file_name.lower().endswith((".mp4", ".mkv", ".mov")):
        await status.edit_text("🎬 Uploading to Bunny Stream...")
        vid_id = await upload_to_stream(path, file_name)
        await status.edit_text(f"✅ Video Streaming Ready! ID: {vid_id}")

    os.remove(path)

print("Userbot is running...")
app.run()
