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

def create_progress_bar(percentage):
    """Create a visual progress bar"""
    filled = int(percentage / 8.33)  # 12 blocks total
    empty = 12 - filled
    bar = "◼️" * filled + "◻️" * empty
    return bar

def format_size(size_bytes):
    """Format bytes to human readable"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.2f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.2f}MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f}GB"

def get_progress_message(percentage, speed, processed, total, eta):
    """Create fancy progress message"""
    bar = create_progress_bar(percentage)
    return f"""╭───⌯═════ 𝐁𝐎𝐓 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒 ═════⌯
├  {percentage:.1f}% {bar}
├
├ 🛜  𝗦𝗣𝗘𝗘𝗗 ➤ | {speed}
├ ♻️  𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗘𝗗 ➤ | {processed}
├ 📦  𝗦𝗜𝗭𝗘 ➤ | {total}
├ ⏰  𝗘𝗧𝗔 ➤ | {eta}
├
╰─═══  𝐂𝐥𝐚𝐬𝐬𝐩𝐥𝐮𝐬 𝐁𝐨𝐭 ═══─╯"""

@bot.on_message(filters.command("start"))
async def start_handler(client, m: Message):
    await m.reply_text(
        "👋 **Welcome to Classplus Token Bot!**\n\n"
        "I can download Classplus content using your token.\n\n"
        "**Commands:**\n"
        "1️⃣ `/token your_jwt_token` - Set your Classplus token\n"
        "2️⃣ `/batch BatchName` - Set batch name for captions\n"
        "3️⃣ Send a `.txt` file with video/PDF links\n"
        "4️⃣ Choose quality and I'll download everything!"
    )

@bot.on_message(filters.command("token"))
async def token_handler(client, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("❌ Please provide the token: `/token your_token_here`")
    
    token = m.text.split(None, 1)[1].strip()
    user_data[m.from_user.id] = {"token": token}
    await m.reply_text("✅ Token saved!\n\nNow use `/batch BatchName` to set batch name, then send a `.txt` file.")

@bot.on_message(filters.command("batch"))
async def batch_handler(client, m: Message):
    user_id = m.from_user.id
    if user_id not in user_data:
        return await m.reply_text("❌ Please set your token first using `/token`")
    
    if len(m.command) < 2:
        return await m.reply_text("❌ Please provide batch name: `/batch PSI Rapid Revision`")
    
    batch_name = m.text.split(None, 1)[1].strip()
    user_data[user_id]["batch_name"] = batch_name
    await m.reply_text(f"✅ Batch name set to: **{batch_name}**\n\nNow send me a `.txt` file containing video/PDF links.")

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
    
    # Parse links - handles format: "Title: URL" or just "URL"
    lines = content.strip().split('\n')
    links = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Skip thumbnail lines
        if line.lower().startswith("thumbnail:"):
            continue
            
        # Check if line contains a URL
        if "http://" in line or "https://" in line:
            # Find where the URL starts
            if "https://" in line:
                url_start = line.find("https://")
            else:
                url_start = line.find("http://")
            
            url = line[url_start:].strip()
            name = line[:url_start].strip()
            
            # Clean up the name (remove trailing colon, dash, etc.)
            name = name.rstrip(":- ").strip()
            if not name:
                name = f"File_{len(links)+1}"
            
            links.append({"name": name, "url": url})
    
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

@bot.on_message(filters.text & ~filters.command(["start", "token", "batch"]))
async def quality_handler(client, m: Message):
    user_id = m.from_user.id
    if user_id not in user_data or "links" not in user_data[user_id]:
        return

    quality = m.text.strip().lower()
    links = user_data[user_id]["links"]
    token = user_data[user_id]["token"]
    batch_name = user_data[user_id].get("batch_name", "Classplus Batch")
    
    # Selection of yt-dlp format
    if quality == "worst":
        ytf = "worst"
    elif quality.isdigit():
        ytf = f"b[height<={quality}]/bv[height<={quality}]+ba/b/bv+ba"
    else:
        ytf = "best"
             
    await m.reply_text(f"🚀 Starting download of {len(links)} items at **{quality}** quality...")
    
    def get_caption(index, title, is_video=True):
        icon = "🎞️" if is_video else "📄"
        return f"""🏷️ Iɴᴅᴇx ID  : {str(index).zfill(3)}

{icon}  Tɪᴛʟᴇ : {title}

📚  𝗕ᴀᴛᴄʜ : {batch_name}

🎓  Uᴘʟᴏᴀᴅ Bʏ : Classplus Bot"""
    
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
                await m.reply_document(file_name, caption=get_caption(i, name, is_video=False))
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
                        
                        # Create progress message
                        progress_msg = await m.reply_text(get_progress_message(0, "0MB/s", "0MB", "Calculating...", "Calculating..."))
                        
                        # Run yt-dlp with aria2c for FAST downloads (16 connections)
                        cmd = f'yt-dlp -f "{ytf}" --newline --progress --external-downloader aria2c --external-downloader-args "-x 16 -s 16 -k 1M" -o "{file_name}" "{signed_url}"'
                        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                        
                        last_update = 0
                        for line in process.stdout:
                            if '[download]' in line and '%' in line:
                                try:
                                    # Parse progress info
                                    parts = line.strip().split()
                                    percent_str = [p for p in parts if '%' in p][0]
                                    percentage = float(percent_str.replace('%', ''))
                                    
                                    # Get size and speed if available
                                    size = "N/A"
                                    speed = "N/A"
                                    eta = "N/A"
                                    processed = "N/A"
                                    
                                    for j, p in enumerate(parts):
                                        if 'MiB' in p or 'GiB' in p or 'KiB' in p:
                                            if j > 0 and 'of' in parts[j-1]:
                                                size = p
                                            else:
                                                processed = p
                                        if '/s' in p:
                                            speed = p
                                        if 'ETA' in p and j+1 < len(parts):
                                            eta = parts[j+1]
                                    
                                    # Update message every 10%
                                    if percentage - last_update >= 10:
                                        last_update = percentage
                                        try:
                                            await progress_msg.edit_text(get_progress_message(percentage, speed, processed, size, eta))
                                        except:
                                            pass
                                except:
                                    pass
                        
                        process.wait()
                        
                        # Final update
                        try:
                            await progress_msg.edit_text(get_progress_message(100, "Done", "Complete", "Complete", "0s"))
                        except:
                            pass
                        
                        if os.path.exists(file_name):
                            await m.reply_video(file_name, caption=get_caption(i, name, is_video=True))
                            os.remove(file_name)
                            await progress_msg.delete()
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
                cmd = f'yt-dlp -f "{ytf}" --external-downloader aria2c --external-downloader-args "-x 16 -s 16 -k 1M" -o "{file_name}" "{url}"'
                subprocess.run(cmd, shell=True, timeout=600)
                if os.path.exists(file_name):
                    await m.reply_video(file_name, caption=get_caption(i, name, is_video=True))
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
