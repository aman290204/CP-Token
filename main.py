# Standalone Token Bot - Uses same patterns as original ITsGOLU bot
import os
import re
import time
import subprocess
import threading
import asyncio
import aiohttp
import aiofiles
import requests
from flask import Flask
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

# Bot Client - same config as original
bot = Client(
    "token_bot_v2",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN.strip() if isinstance(BOT_TOKEN, str) else BOT_TOKEN,
    workers=300,
    sleep_threshold=60,
    in_memory=True
)

# User session storage
user_data = {}

# ===== UTILITY FUNCTIONS (from original utils.py) =====

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
    """Same progress bar as original bot"""
    if not timer.can_send():
        return

    now = time.time()
    elapsed = now - start
    if elapsed < 1:
        return

    base_speed = current / elapsed
    speed = base_speed + (9 * 1024 * 1024)  # +9 MB/s boost display

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
        f"╰─═══ ** 𝐂𝐥𝐚𝐬𝐬𝐩𝐥𝐮𝐬 𝐁𝐨𝐭 **═══─╯"
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
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        return float(result.stdout)
    except:
        return 0

# ===== DOWNLOAD FUNCTION (same as original) =====

async def download_video(url, cmd, name):
    """Same download function as original - uses aria2c with 16 connections"""
    retry_count = 0
    max_retries = 2

    while retry_count < max_retries:
        download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
        print(download_cmd)
        k = subprocess.run(download_cmd, shell=True)
        if k.returncode == 0:
            break
        retry_count += 1
        print(f"⚠️ Download failed (attempt {retry_count}/{max_retries}), retrying in 5s...")
        await asyncio.sleep(5)

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

# ===== SEND VIDEO FUNCTION (same as original) =====

async def send_vid(bot, m, cc, filename, thumb, name, prog, channel_id):
    """Same send_vid as original bot with progress callback"""
    try:
        thumbnail = None
        temp_thumb = f"downloads/thumb_{os.path.basename(filename)}.jpg"
        
        # Generate thumbnail
        os.makedirs("downloads", exist_ok=True)
        subprocess.run(
            f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 -y "{temp_thumb}"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(temp_thumb):
            thumbnail = temp_thumb

        await prog.delete(True)

        reply1 = await bot.send_message(channel_id, f" **Uploading Video:**\n<blockquote>{name}</blockquote>")
        reply = await m.reply_text(f"🖼 **Generating Thumbnail:**\n<blockquote>{name}</blockquote>")

        dur = int(duration(filename))
        start_time = time.time()

        try:
            sent_message = await bot.send_video(
                chat_id=channel_id,
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
        except Exception:
            sent_message = await bot.send_document(
                chat_id=channel_id,
                document=filename,
                caption=cc,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )

        # Cleanup
        if os.path.exists(filename):
            os.remove(filename)
        await reply.delete(True)
        await reply1.delete(True)
        if thumbnail and os.path.exists(thumbnail):
            os.remove(thumbnail)

        return sent_message

    except Exception as err:
        raise Exception(f"send_vid failed: {err}")

# ===== BOT HANDLERS =====

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
    b_name = user_data[user_id].get("batch_name", "Classplus Batch")
    
    editable = await m.reply_text("📥 Downloading file...")
    file_path = await m.download()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    os.remove(file_path)
    
    # Parse links (same as original bot)
    content = content.split("\n")
    content = [line.strip() for line in content if line.strip()]
    
    links = []
    for i in content:
        if "://" in i:
            if i.strip().startswith("Thumbnail:"):
                continue
            parts = i.split("://", 1)
            if len(parts) == 2:
                name = parts[0]
                url = "://" + parts[1]
                # Find the actual URL start
                if "https" in name:
                    name = name.split("https")[0]
                    url = "https://" + parts[1]
                elif "http" in name:
                    name = name.split("http")[0]
                    url = "http://" + parts[1]
                name = name.rstrip(":- ").strip()
                if not name:
                    name = f"File_{len(links)+1}"
                links.append([name, url])
    
    if not links:
        return await editable.edit("❌ No valid links found in the file.")
    
    user_data[user_id]["links"] = links
    user_data[user_id]["b_name"] = b_name
    
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

    raw_text2 = m.text.strip()
    links = user_data[user_id]["links"]
    token = user_data[user_id]["token"]
    b_name = user_data[user_id].get("b_name", "Classplus Batch")
    CR = CREDIT
    channel_id = m.chat.id
    
    # Build resolution format (same as original)
    if raw_text2 == "worst":
        ytf = "worst"
        res = "worst"
    elif raw_text2.isdigit():
        ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
        res = f"{raw_text2}p"
    else:
        ytf = "best"
        res = "best"
    
    await m.reply_text(f"🚀 Starting download of **{len(links)}** items at **{res}** quality...")
    
    count = 1
    failed_count = 0
    
    for link_data in links:
        name = sanitize_filename(link_data[0])
        url = link_data[1].strip()
        name1 = name[:50] if len(name) > 50 else name
        link0 = url
        
        try:
            # Same caption format as original bot
            cc = (
                f"<b>🏷️ Iɴᴅᴇx ID  :</b> {str(count).zfill(3)}\n\n"
                f"<b>🎞️  Tɪᴛʟᴇ :</b> {name1} \n\n"
                f"<blockquote>📚  𝗕ᴀᴛᴄʜ : {b_name}</blockquote>"
                f"\n\n<b>🎓  Uᴘʟᴏᴀᴅ Bʏ : {CR}</b>"
            )
            cc1 = (
                f"<b>🏷️ Iɴᴅᴇx ID :</b> {str(count).zfill(3)}\n\n"
                f"<b>📑  Tɪᴛʟᴇ :</b> {name1} \n\n"
                f"<blockquote>📚  𝗕ᴀᴛᴄʜ : {b_name}</blockquote>"
                f"\n\n<b>🎓  Uᴘʟᴏᴀᴅ Bʏ : {CR}</b>"
            )
            
            # PDF Download
            if ".pdf" in url:
                try:
                    cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                    download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                    os.system(download_cmd)
                    await bot.send_document(chat_id=channel_id, document=f'{name}.pdf', caption=cc1)
                    count += 1
                    os.remove(f'{name}.pdf')
                except FloodWait as e:
                    await m.reply_text(str(e))
                    time.sleep(e.x)
                    continue
            
            # Classplus Video - use AANT API with token
            elif any(x in url for x in ["cpvod.testbook.com", "classplusapp.com", "media-cdn.classplusapp"]):
                url_norm = url.replace("https://cpvod.testbook.com/", "https://media-cdn.classplusapp.com/drm/")
                api_url_call = f"https://cp-api-by-aman.vercel.app/AANT?url={url_norm}&token={token}"
                
                try:
                    resp = requests.get(api_url_call, timeout=30)
                    data = resp.json()
                    
                    # Get the signed URL
                    if isinstance(data, dict) and "url" in data:
                        signed_url = data.get("url")
                    elif isinstance(data, dict) and "MPD" in data:
                        signed_url = data.get("MPD")
                    else:
                        signed_url = url
                    
                    Show = f"<i><b>📥 Fast Video Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                    prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                    
                    cmd = f'yt-dlp -f "{ytf}" -o "{name}.mp4" "{signed_url}"'
                    filename = await download_video(signed_url, cmd, f"{name}.mp4")
                    
                    if os.path.exists(filename):
                        await send_vid(bot, m, cc, filename, "/d", name, prog, channel_id)
                        count += 1
                    else:
                        await bot.send_message(channel_id, f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n**Url** =>> {link0}', disable_web_page_preview=True)
                        failed_count += 1
                        count += 1
                        
                except Exception as e:
                    await bot.send_message(channel_id, f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n\n<blockquote><i><b>Failed Reason: {str(e)}</b></i></blockquote>', disable_web_page_preview=True)
                    count += 1
                    failed_count += 1
                    continue
            
            # Other videos
            else:
                Show = f"<i><b>📥 Fast Video Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                
                cmd = f'yt-dlp -f "{ytf}" -o "{name}.mp4" "{url}"'
                filename = await download_video(url, cmd, f"{name}.mp4")
                
                if os.path.exists(filename):
                    await send_vid(bot, m, cc, filename, "/d", name, prog, channel_id)
                    count += 1
                else:
                    await bot.send_message(channel_id, f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n**Url** =>> {link0}', disable_web_page_preview=True)
                    failed_count += 1
                    count += 1
                
        except Exception as e:
            await bot.send_message(channel_id, f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n\n<blockquote><i><b>Failed Reason: {str(e)}</b></i></blockquote>', disable_web_page_preview=True)
            count += 1
            failed_count += 1
            continue

    # Clear session
    del user_data[user_id]["links"]
    
    # Final summary (same format as original)
    success_count = len(links) - failed_count
    await bot.send_message(
        channel_id,
        (
            "<b>📬 ᴘʀᴏᴄᴇꜱꜱ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n\n"
            "<blockquote><b>📚 ʙᴀᴛᴄʜ ɴᴀᴍᴇ :</b> "
            f"{b_name}</blockquote>\n"
            
            "╭────────────────\n"
            f"├ 🖇️ ᴛᴏᴛᴀʟ ᴜʀʟꜱ : <code>{len(links)}</code>\n"
            f"├ ✅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ : <code>{success_count}</code>\n"
            f"├ ❌ ꜰᴀɪʟᴇᴅ : <code>{failed_count}</code>\n"
            "╰────────────────\n\n"
            f"<b>🎓 Uᴘʟᴏᴀᴅᴇᴅ Bʏ : {CR}</b>"
        )
    )

def run_flask():
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    bot.run()
