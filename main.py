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

@bot.on_message(filters.command("start"))
async def start_handler(client, m: Message):
    await m.reply_text(
        "👋 **Welcome to Classplus Token Bot!**\n\n"
        "I can download Classplus content using your token.\n\n"
        "**Commands:**\n"
        "1️⃣ `/token your_jwt_token` - Set your Classplus token\n"
        "2️⃣ Send a `.txt` file with video/PDF links\n"
        "3️⃣ Choose quality and I'll download everything!"
    )

@bot.on_message(filters.command("token"))
async def token_handler(client, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("❌ Please provide the token: `/token your_token_here`")
    
    token = m.text.split(None, 1)[1].strip()
    user_data[m.from_user.id] = {"token": token}
    await m.reply_text("✅ Token saved!\n\nNow send me a `.txt` file containing video/PDF links.")

@bot.on_message(filters.document)
async def txt_handler(client, m: Message):
    user_id = m.from_user.id
    
    # Check if it's a txt file
    if not m.document.file_name.endswith('.txt'):
        return await m.reply_text("❌ Please send a `.txt` file with links.")
    
    # Check if token is set
    if user_id not in user_data or "token" not in user_data[user_id]:
        return await m.reply_text("❌ Please set your token first using `/token your_token`")
    
    token = user_data[user_id]["token"]
    
    # Download the txt file
    editable = await m.reply_text("📥 Downloading file...")
    file_path = await m.download()
    
    # Read links from file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    os.remove(file_path)
    
    # Parse links
    lines = content.strip().split('\n')
    links = []
    current_name = "Untitled"
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("Name:"):
            current_name = line.replace("Name:", "").strip()
        elif line.startswith("http") or line.startswith("https"):
            links.append({"name": current_name, "url": line})
    
    if not links:
        return await editable.edit("❌ No valid links found in the file.")
    
    user_data[user_id]["links"] = links
    
    await editable.edit(
        f"✅ Found **{len(links)}** links!\n\n"
        "🎞️ **Enter Resolution:**\n\n"
        "╭━━⪼ `worst`\n"
        "┣━━⪼ `144`\n"
        "┣━━⪼ `240`\n"
        "┣━━⪼ `360`\n"
        "┣━━⪼ `480`\n"
        "┣━━⪼ `720`\n"
        "╰━━⪼ `1080`\n\n"
        "Send the number (e.g., `480`) or `worst`."
    )

@bot.on_message(filters.text & ~filters.command(["start", "token"]))
async def quality_handler(client, m: Message):
    user_id = m.from_user.id
    if user_id not in user_data or "links" not in user_data[user_id]:
        return

    quality = m.text.strip().lower()
    links = user_data[user_id]["links"]
    token = user_data[user_id]["token"]
    
    # Selection of yt-dlp format
    if quality == "worst":
        ytf = "worst"
    elif quality.isdigit():
        ytf = f"b[height<={quality}]/bv[height<={quality}]+ba/b/bv+ba"
    else:
        ytf = "best"
             
    await m.reply_text(f"🚀 Starting download of {len(links)} items at **{quality}** quality...")
    
    for i, item in enumerate(links, 1):
        name = item.get('name', f'Video_{i}')
        url = item.get('url', '')
        
        if not url:
            continue
        
        await m.reply_text(f"📥 [{i}/{len(links)}] Processing: {name}")
            
        # PDF Download
        if ".pdf" in url.lower():
            file_name = f"{sanitize_filename(name)}.pdf"
            try:
                resp = requests.get(url, timeout=60)
                with open(file_name, "wb") as f:
                    f.write(resp.content)
                await m.reply_document(file_name, caption=f"📄 {name}")
                os.remove(file_name)
            except Exception as e:
                await m.reply_text(f"❌ Error downloading PDF: {str(e)}")
            
        # Video Download (using AANT API for signing)
        elif "m3u8" in url or "mpd" in url or "classplusapp" in url:
            # Normalize for AANT
            url_norm = url.replace("https://cpvod.testbook.com/", "https://media-cdn.classplusapp.com/drm/")
            api_call = f"https://cp-api-by-aman.vercel.app/AANT?url={url_norm}&token={token}"
            
            try:
                resp = requests.get(api_call, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_url = data.get('url') or data.get('MPD') or data.get('m3u8')
                    if signed_url:
                        file_name = f"{sanitize_filename(name)}.mp4"
                        cmd = f'yt-dlp -f "{ytf}" -o "{file_name}" "{signed_url}"'
                        subprocess.run(cmd, shell=True, timeout=600)
                        
                        if os.path.exists(file_name):
                            await m.reply_video(file_name, caption=f"🎥 {name}")
                            os.remove(file_name)
                        else:
                            await m.reply_text(f"❌ Failed to download: {name}")
                    else:
                        await m.reply_text(f"⚠️ API did not return URL for: {name}")
                else:
                    await m.reply_text(f"⚠️ API error ({resp.status_code}): {name}")
            except Exception as e:
                await m.reply_text(f"❌ Error: {str(e)}")
        
        # Direct video URL
        elif any(ext in url.lower() for ext in ['.mp4', '.mkv', '.webm']):
            file_name = f"{sanitize_filename(name)}.mp4"
            try:
                cmd = f'yt-dlp -f "{ytf}" -o "{file_name}" "{url}"'
                subprocess.run(cmd, shell=True, timeout=600)
                if os.path.exists(file_name):
                    await m.reply_video(file_name, caption=f"🎥 {name}")
                    os.remove(file_name)
            except Exception as e:
                await m.reply_text(f"❌ Error: {str(e)}")

    # Clear links to prevent re-processing
    del user_data[user_id]["links"]
    await m.reply_text("🎯 **All downloads complete!**")


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
