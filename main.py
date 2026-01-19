import os
import re
import time
import subprocess
import threading
import requests
import logging
from flask import Flask
from math import ceil
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from vars import API_ID, API_HASH, BOT_TOKEN, CREDIT

# Flask app for Render health check
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/health')
def health():
    return 'OK'

# Bot Configuration
bot = Client(
    "token_bot_v2",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN.strip()
)

# In-memory storage
user_data = {}

# ==================== UTILS FROM ORIGINAL BOT ====================

class Timer:
    def __init__(self, time_between=5):
        self.start_time = time.time()
        self.time_between = time_between

    def can_send(self):
        if time.time() > (self.start_time + self.time_between):
            self.start_time = time.time()
            return True
        return False

timer = Timer()

def hrb(value, digits=2, delim="", postfix=""):
    if value is None:
        return None
    chosen_unit = "B"
    for unit in ("KB", "MB", "GB", "TB"):
        if value > 1000:
            value /= 1024
            chosen_unit = unit
        else:
            break
    return f"{value:.{digits}f}" + delim + chosen_unit + postfix

def hrt(seconds, precision=0):
    pieces = []
    from datetime import timedelta
    value = timedelta(seconds=seconds)
    if value.days:
        pieces.append(f"{value.days}d")
    seconds = value.seconds
    if seconds >= 3600:
        hours = int(seconds / 3600)
        pieces.append(f"{hours}h")
        seconds -= hours * 3600
    if seconds >= 60:
        minutes = int(seconds / 60)
        pieces.append(f"{minutes}m")
        seconds -= minutes * 60
    if seconds > 0 or not pieces:
        pieces.append(f"{seconds}s")
    if not precision:
        return "".join(pieces)
    return "".join(pieces[:precision])

async def progress_bar(current, total, reply, start):
    if not timer.can_send():
        return

    now = time.time()
    elapsed = now - start
    if elapsed < 1:
        return

    base_speed = current / elapsed
    speed = base_speed + (9 * 1024 * 1024)  # +9 MB/s boost

    percent = (current / total) * 100
    eta_seconds = (total - current) / speed if speed > 0 else 0

    bar_length = 12
    progress_ratio = current / total
    filled_length = progress_ratio * bar_length

    progress_bar_list = []
    for i in range(bar_length):
        pos = i + 1
        if pos <= int(filled_length):
            if progress_ratio > 0.7:
                progress_bar_list.append("🔳")
            else:
                progress_bar_list.append("🔲")
        elif pos - 1 < filled_length < pos:
            progress_bar_list.append("◻️")
        else:
            progress_bar_list.append("◻️")

    if progress_ratio >= 0.9:
        for i in range(int(filled_length)):
            progress_bar_list[i] = "◻️"

    progress_bar_str = "".join(progress_bar_list)

    msg = (
        f"╭───⌯═════ 𝐁𝐎𝐓 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒 ═════⌯\n"
        f"├  **{percent:.1f}%** `{progress_bar_str}`\n├\n"
        f"├ 🛜  𝗦𝗣𝗘𝗘𝗗 ➤ | {hrb(speed)}/s \n"
        f"├ ♻️  𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗘𝗗 ➤ | {hrb(current)} \n"
        f"├ 📦  𝗦𝗜𝗭𝗘 ➤ | {hrb(total)} \n"
        f"├ ⏰  𝗘𝗧𝗔 ➤ | {hrt(eta_seconds, 1)}\n\n"
        f"╰─═══ ** {CREDIT} **═══─╯"
    )

    try:
        await reply.edit(msg)
    except FloodWait as e:
        time.sleep(e.x)
    except:
        pass

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    try:
        return float(result.stdout)
    except:
        return 0

def get_duration(filename):
    return duration(filename)

def split_large_video(file_path, max_size_mb=1900):
    size_bytes = os.path.getsize(file_path)
    max_bytes = max_size_mb * 1024 * 1024

    if size_bytes <= max_bytes:
        return [file_path]

    dur = get_duration(file_path)
    parts = ceil(size_bytes / max_bytes)
    part_duration = dur / parts
    base_name = file_path.rsplit(".", 1)[0]
    output_files = []

    for i in range(parts):
        output_file = f"{base_name}_part{i+1}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-ss", str(int(part_duration * i)),
            "-t", str(int(part_duration)),
            "-c", "copy",
            output_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_file):
            output_files.append(output_file)

    return output_files

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

async def download_video(url, cmd, name):
    retry_count = 0
    max_retries = 2

    while retry_count < max_retries:
        download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
        print(download_cmd)
        k = subprocess.run(download_cmd, shell=True)
        if k.returncode == 0:
            break
        retry_count += 1
        print(f"⚠️ Download failed (attempt {retry_count}/{max_retries}), retrying...")
        time.sleep(5)

    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"
        return name + ".mp4"
    except:
        return name

async def send_vid(bot, m, cc, filename, thumb, name, prog):
    try:
        temp_thumb = None
        thumbnail = thumb

        if thumb in ["/d", "no"] or not os.path.exists(str(thumb)):
            temp_thumb = f"thumb_{os.path.basename(filename)}.jpg"
            subprocess.run(
                f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 -y "{temp_thumb}"',
                shell=True
            )
            thumbnail = temp_thumb if os.path.exists(temp_thumb) else None

        await prog.delete(True)
        reply = await m.reply_text(f"📤 **Uploading:**\n<blockquote>{name}</blockquote>")

        file_size_mb = os.path.getsize(filename) / (1024 * 1024)

        if file_size_mb < 2000:
            dur = int(duration(filename))
            start_time = time.time()

            try:
                sent_message = await bot.send_video(
                    chat_id=m.chat.id,
                    video=filename,
                    caption=cc,
                    supports_streaming=True,
                    height=720,
                    width=1280,
                    thumb=thumbnail,
                    duration=dur,
                    progress=progress_bar,
                    progress_args=(reply, start_time)
                )
            except:
                sent_message = await bot.send_document(
                    chat_id=m.chat.id,
                    document=filename,
                    caption=cc,
                    progress=progress_bar,
                    progress_args=(reply, start_time)
                )

            if os.path.exists(filename):
                os.remove(filename)
            await reply.delete(True)

        else:
            notify_split = await m.reply_text(
                f"⚠️ Video larger than 2GB ({human_readable_size(os.path.getsize(filename))})\n"
                f"⏳ Splitting into parts..."
            )
            parts = split_large_video(filename)

            for idx, part in enumerate(parts):
                part_dur = int(duration(part))
                part_caption = f"{cc}\n\n📦 Part {idx+1} of {len(parts)}"
                upload_msg = await m.reply_text(f"📤 Uploading Part {idx+1}/{len(parts)}...")

                try:
                    await bot.send_video(
                        chat_id=m.chat.id,
                        video=part,
                        caption=part_caption,
                        supports_streaming=True,
                        thumb=thumbnail,
                        duration=part_dur,
                        progress=progress_bar,
                        progress_args=(upload_msg, time.time())
                    )
                except:
                    await bot.send_document(
                        chat_id=m.chat.id,
                        document=part,
                        caption=part_caption,
                        progress=progress_bar,
                        progress_args=(upload_msg, time.time())
                    )

                await upload_msg.delete(True)
                if os.path.exists(part):
                    os.remove(part)

            await reply.delete(True)
            await notify_split.delete(True)
            if os.path.exists(filename):
                os.remove(filename)

        if temp_thumb and os.path.exists(temp_thumb):
            os.remove(temp_thumb)

    except Exception as err:
        await m.reply_text(f"❌ Upload failed: {err}")

# ==================== BOT HANDLERS ====================

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
    
    if not m.document.file_name.endswith('.txt'):
        return await m.reply_text("❌ Please send a `.txt` file with links.")
    
    if user_id not in user_data or "token" not in user_data[user_id]:
        return await m.reply_text("❌ Please set your token first using `/token your_token`")
    
    token = user_data[user_id]["token"]
    
    editable = await m.reply_text("📥 Downloading file...")
    file_path = await m.download()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    os.remove(file_path)
    
    # Parse links
    lines = content.strip().split('\n')
    links = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("thumbnail:"):
            continue
        if "http://" in line or "https://" in line:
            if "https://" in line:
                url_start = line.find("https://")
            else:
                url_start = line.find("http://")
            
            url = line[url_start:].strip()
            name = line[:url_start].strip().rstrip(":- ").strip()
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
    
    # yt-dlp format
    if quality == "worst":
        ytf = "worst"
    elif quality.isdigit():
        ytf = f"b[height<={quality}]/bv[height<={quality}]+ba/b/bv+ba"
    else:
        ytf = "best"
    
    def get_caption(index, title, is_video=True):
        icon = "🎞️" if is_video else "📄"
        return f"""🏷️ Iɴᴅᴇx ID  : {str(index).zfill(3)}

{icon}  Tɪᴛʟᴇ : {title}

📚  𝗕ᴀᴛᴄʜ : {batch_name}

🎓  Uᴘʟᴏᴀᴅ Bʏ : {CREDIT}"""
             
    await m.reply_text(f"🚀 Starting download of {len(links)} items at **{quality}** quality...")
    
    for i, item in enumerate(links, 1):
        name = item.get('name', f'Video_{i}')
        url = item.get('url', '')
        
        if not url:
            continue
        
        prog = await m.reply_text(f"📥 [{i}/{len(links)}] Processing: {name}")
            
        # PDF Download
        if ".pdf" in url.lower():
            file_name = f"{sanitize_filename(name)}.pdf"
            try:
                resp = requests.get(url, timeout=120)
                with open(file_name, "wb") as f:
                    f.write(resp.content)
                await m.reply_document(file_name, caption=get_caption(i, name, is_video=False))
                os.remove(file_name)
                await prog.delete()
            except Exception as e:
                await prog.edit(f"❌ Error downloading PDF: {str(e)}")
            
        # Video Download (using AANT API for signing)
        elif "m3u8" in url or "mpd" in url or "classplusapp" in url:
            url_norm = url.replace("https://cpvod.testbook.com/", "https://media-cdn.classplusapp.com/drm/")
            api_call = f"https://cp-api-by-aman.vercel.app/AANT?url={url_norm}&token={token}"
            
            try:
                resp = requests.get(api_call, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_url = data.get('url') or data.get('MPD') or data.get('m3u8')
                    if signed_url:
                        file_name = f"{sanitize_filename(name)}.mp4"
                        
                        # Download with aria2c (fast!)
                        cmd = f'yt-dlp -f "{ytf}" -o "{file_name}" -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32" "{signed_url}"'
                        downloaded_file = await download_video(signed_url, f'yt-dlp -f "{ytf}" -o "{file_name}"', file_name)
                        
                        if os.path.exists(downloaded_file):
                            await send_vid(client, m, get_caption(i, name, is_video=True), downloaded_file, "/d", name, prog)
                        else:
                            await prog.edit(f"❌ Failed to download: {name}")
                    else:
                        await prog.edit(f"⚠️ API did not return URL for: {name}")
                else:
                    await prog.edit(f"⚠️ API error ({resp.status_code}): {name}")
            except Exception as e:
                await prog.edit(f"❌ Error: {str(e)}")
        
        # Direct video URL
        elif any(ext in url.lower() for ext in ['.mp4', '.mkv', '.webm']):
            file_name = f"{sanitize_filename(name)}.mp4"
            try:
                downloaded_file = await download_video(url, f'yt-dlp -f "{ytf}" -o "{file_name}"', file_name)
                if os.path.exists(downloaded_file):
                    await send_vid(client, m, get_caption(i, name, is_video=True), downloaded_file, "/d", name, prog)
            except Exception as e:
                await prog.edit(f"❌ Error: {str(e)}")

    del user_data[user_id]["links"]
    await m.reply_text("🎯 **All downloads complete!**")


def run_flask():
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    bot.run()
