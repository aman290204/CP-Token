import os
import requests
import asyncio
import subprocess
import re
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from vars import API_ID, API_HASH, BOT_TOKEN

# Flask app for Render health check
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/health')
def health():
    return 'OK'

# Standalone Bot Configuration
# Uses your existing credentials from vars.py
bot = Client(
    "token_bot_v2",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN.strip()
)

# In-memory storage for user session
user_data = {}

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

async def fetch_content(token, batch_id):
    """
    Attempts to fetch content list from Classplus.
    Includes common endpoints used by Classplus.
    """
    headers = {
        'x-access-token': token,
        'api-version': '18',
        'region': 'IN'
    }
    
    # Try multiple common endpoints
    endpoints = [
        f'https://api.classplusapp.com/v2/course/content/get-batch-content-details?batchId={batch_id}&limit=1000',
        f'https://api.classplusapp.com/v2/course/content/get-course-content-by-batch-id?batchId={batch_id}',
        f'https://api.classplusapp.com/v2/batches/{batch_id}/hierarchy'
    ]
    
    for url in endpoints:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Classplus typically returns a list of items in 'data' or 'items'
                items = data.get('data', {}).get('items', []) or data.get('items', [])
                if items:
                    return items
        except Exception:
            continue
    return None

@bot.on_message(filters.command("start"))
async def start_handler(client, m: Message):
    await m.reply_text("👋 **Welcome to Standalone Token Bot!**\n\nI can fetch and download Classplus content automatically.\n\nSend /token followed by your JWT token to begin.")

@bot.on_message(filters.command("token"))
async def token_handler(client, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("❌ Please provide the token: `/token your_token_here`")
    
    token = m.text.split(None, 1)[1].strip()
    user_data[m.from_user.id] = {"token": token}
    await m.reply_text("✅ Token saved! Now send /batch followed by the Batch ID.")

@bot.on_message(filters.command("batch"))
async def batch_handler(client, m: Message):
    user_id = m.from_user.id
    if user_id not in user_data or "token" not in user_data[user_id]:
        return await m.reply_text("❌ Please set your token first using /token")
    
    if len(m.command) < 2:
        return await m.reply_text("❌ Please provide Batch ID: `/batch 777056`")
    
    batch_id = m.command[1]
    token = user_data[user_id]["token"]
    
    editable = await m.reply_text(f"🔍 Fetching content for Batch `{batch_id}`...")
    
    items = await fetch_content(token, batch_id)
    if not items:
        return await editable.edit("⚠️ Failed to fetch content automatically. Classplus API structure might be different for this organization.")
    
    user_data[user_id]["items"] = items
    user_data[user_id]["batch_id"] = batch_id
    
    await editable.edit("🎞️ **Enter Resolution**\n\n╭━━⪼ `worst`\n┣━━⪼ `144`\n┣━━⪼ `240`\n┣━━⪼ `360`\n┣━━⪼ `480`\n┣━━⪼ `720`\n╰━━⪼ `1080`\n\nSend the number (e.g., `480`) or `worst`.")

@bot.on_message(filters.text & ~filters.command(["start", "token", "batch"]))
async def quality_handler(client, m: Message):
    user_id = m.from_user.id
    if user_id not in user_data or "items" not in user_data[user_id]:
        return

    quality = m.text.strip().lower()
    items = user_data[user_id]["items"]
    token = user_data[user_id]["token"]
    
    # Selection of yt-dlp format
    if quality == "worst":
        ytf = "worst"
    else:
        # standard extraction: b[height<=720]/...
        ytf = f"b[height<={quality}]/bv[height<={quality}]+ba/b/bv+ba"
        if not quality.isdigit():
             ytf = "best" # fallback
             
    await m.reply_text(f"🚀 Starting download of {len(items)} items at **{quality}** quality...")
    
    for item in items:
        name = item.get('name', 'Untitled')
        url = item.get('url') or item.get('contentUrl')
        
        if not url:
            continue
            
        # PDF Download
        if ".pdf" in url:
            file_name = f"{sanitize_filename(name)}.pdf"
            try:
                resp = requests.get(url)
                with open(file_name, "wb") as f:
                    f.write(resp.content)
                await m.reply_document(file_name, caption=f"📄 {name}")
                os.remove(file_name)
            except Exception as e:
                await m.reply_text(f"❌ Error downloading PDF {name}: {str(e)}")
            
        # Video Download (using AANT API for signing)
        elif "m3u8" in url or "mpd" in url:
            # Normalize for AANT
            url_norm = url.replace("https://cpvod.testbook.com/", "https://media-cdn.classplusapp.com/drm/")
            api_call = f"https://cp-api-by-aman.vercel.app/AANT?url={url_norm}&token={token}"
            
            try:
                resp = requests.get(api_call)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_url = data.get('url') or data.get('MPD')
                    if signed_url:
                        file_name = f"{sanitize_filename(name)}.mp4"
                        cmd = f'yt-dlp -f "{ytf}" -o "{file_name}" "{signed_url}"'
                        subprocess.run(cmd, shell=True)
                        
                        if os.path.exists(file_name):
                            await m.reply_video(file_name, caption=f"🎥 {name}")
                            os.remove(file_name)
                        else:
                            await m.reply_text(f"❌ Failed to download video: {name}")
                    else:
                        await m.reply_text(f"⚠️ API did not return a valid URL for: {name}")
                else:
                    await m.reply_text(f"⚠️ API error ({resp.status_code}) for: {name}")
            except Exception as e:
                await m.reply_text(f"❌ Error processing video {name}: {str(e)}")

    # Clear items to prevent re-processing on random text
    del user_data[user_id]["items"]
    await m.reply_text("🎯 **Batch processing complete!**")


def run_flask():
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run the bot
    bot.run()
