import os
import asyncio
import requests
from pyrogram import Client, filters

# --- CONFIGURATION (Loaded from GitHub Secrets) ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")
BUNNY_API_KEY = os.getenv("BUNNY_API_KEY")

app = Client(
    "bunny_bot", 
    session_string=SESSION_STRING, 
    api_id=API_ID, 
    api_hash=API_HASH
)

# Queue to handle multiple forwards sequentially
video_queue = asyncio.Queue()

def upload_to_bunny(file_path, video_name):
    """Handles the Bunny.net Stream API logic."""
    url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
    headers = {
        "accept": "application/json", 
        "content-type": "application/json", 
        "AccessKey": BUNNY_API_KEY
    }
    
    try:
        # 1. Create the video object in Bunny
        response = requests.post(url, json={"title": video_name}, headers=headers).json()
        video_id = response.get("guid")

        if not video_id:
            return None

        # 2. Upload the video file binary
        upload_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video_id}"
        with open(file_path, 'rb') as f:
            res = requests.put(upload_url, data=f, headers={"AccessKey": BUNNY_API_KEY})
        
        return video_id if res.status_code == 200 else None
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

async def worker():
    """Background worker that processes the queue."""
    while True:
        message, status_msg = await video_queue.get()
        
        try:
            await status_msg.edit("📥 **Downloading from Telegram...**")
            # Download to local disk
            file_path = await message.download()
            file_name = os.path.basename(file_path)
            
            await status_msg.edit(f"📤 **Uploading to Bunny:**\n`{file_name}`")
            video_id = upload_to_bunny(file_path, file_name)
            
            if video_id:
                # Constructing the public player link
                playback_url = f"https://iframe.mediadelivery.net/play/{BUNNY_LIBRARY_ID}/{video_id}"
                
                await status_msg.edit(
                    f"✅ **Upload Complete!**\n\n"
                    f"🎥 **File:** `{file_name}`\n"
                    f"🔗 **Link:** {playback_url}\n"
                    f"🛠 **Panel:** [View in Bunny](https://panel.bunny.net/stream/{BUNNY_LIBRARY_ID}/videos/{video_id})"
                )
            else:
                await status_msg.edit(f"❌ **Upload Failed:** `{file_name}`")
            
            # CRITICAL: Delete file to free GitHub disk space
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Successfully cleaned up: {file_name}")

        except Exception as e:
            await status_msg.edit(f"⚠️ **Error:** {str(e)}")
        
        # Mark task as done
        video_queue.task_done()

@app.on_message(filters.me & filters.video)
async def queue_handler(client, message):
    """Triggers when you forward a video to your Saved Messages or any chat."""
    status_msg = await message.reply("⏳ **Added to queue...**", quote=True)
    await video_queue.put((message, status_msg))

async def main():
    async with app:
        # Start the queue worker in the background
        asyncio.create_task(worker())
        print("Bot is running... Forward a video to start.")
        # Keep the bot alive
        await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
