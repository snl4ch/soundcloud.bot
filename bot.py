# Gemini 3.1 Pro

import os
import re
import time
import yt_dlp
import asyncio
import aiohttp

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.client.session.aiohttp import AiohttpSession

from aiogram.types import (
    Message,
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    ChosenInlineResult,
    InputMediaAudio,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

load_dotenv()

session = AiohttpSession(timeout=300, proxy=os.getenv("PROXY"))
bot = Bot(token=os.getenv("TOKEN"), session=session)
dp = Dispatcher()

url_cache = {}

def format_duration(seconds) -> str:
    if not seconds:
        return "0:00"
    
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

def search_soundcloud(query: str, limit: int = 10) -> list:
    ydl_opts = {
        "format": "bestaudio/best", 
        "extract_flat": True, 
        "quiet": True, 
        "socket_timeout": 15
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
        return result.get("entries", [])

def download_track(url: str, inline_id: str = None, title: str = "", artist: str = "", loop=None) -> dict:
    last_update = time.time()
    
    def progress_hook(d):
        nonlocal last_update
        
        if d["status"] == "downloading" and inline_id and loop:
            now = time.time()
            
            if now - last_update > 1.1:
                last_update = now
                percent_clean = ""
                
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                
                if total and total > 0:
                    percent_clean = f"{(downloaded / total) * 100:.1f}%"
                elif d.get("fragment_count") and d.get("fragment_index"):
                    percent_clean = f"{(d['fragment_index'] / d['fragment_count']) * 100:.1f}%"
                else:
                    percent_str = d.get("_percent_str", "")
                    percent_clean = re.sub(r"\x1b\[[0-9;]*m", "", percent_str).strip()
                
                if percent_clean:
                    new_text = f"⬇️ <b>{artist} — {title}</b> <i>Downloading: {percent_clean}</i>"
                    
                    async def update_msg():
                        try:
                            await bot.edit_message_text(
                                inline_message_id=inline_id,
                                text=new_text,
                                parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ InlineKeyboardButton(text="Downloading...", callback_data="loading") ]])
                            )
                        except:
                            pass
                        
                    asyncio.run_coroutine_threadsafe(update_msg(), loop)

        elif d["status"] == "finished" and inline_id and loop:
            new_text = f"⚙️ <b>{artist} — {title}</b> <i>Processing...</i>"
            
            async def update_msg_finished():
                try:
                    await bot.edit_message_text(
                        inline_message_id=inline_id,
                        text=new_text,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ InlineKeyboardButton(text="Processing...", callback_data="loading") ]])
                    )
                except:
                    pass
                
            asyncio.run_coroutine_threadsafe(update_msg_finished(), loop)

    ydl_opts = {
        "format": "bestaudio/best",
        "external_downloader": "aria2c",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "writethumbnail": True, 
        "concurrent_fragment_downloads": 3,
        "socket_timeout": 15,
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"}
        ]
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        raw_duration = info.get("duration", 0)
        safe_duration = int(raw_duration) if raw_duration else 0
        
        raw_thumb = info.get("thumbnails", [{}])[-1].get("url", "")
        safe_thumb = raw_thumb.replace("t500x500", "t300x300").replace("crop", "t300x300").replace("large", "t300x300").replace("original", "t300x300") if raw_thumb else None
        
        return {
            "path": f"downloads/{info['id']}.m4a",
            "title": info.get("title", "Unknown"),
            "artist": info.get("uploader", "Unknown Artist"),
            "duration": safe_duration,
            "thumbnail": safe_thumb 
        }

@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = "🤓 Msg anywhere <b>@loadsongbot s0Ng nAm3</b> to search any music on soundclout"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Search", switch_inline_query="")]])
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@dp.inline_query()
async def inline_search(query: InlineQuery):
    search_text = query.query.strip()
    
    if not search_text:
        await query.answer([
            InlineQueryResultArticle(
                id="empty_query",
                title="👀 Start typing...",
                description="For example: Yeat",
                input_message_content=InputTextMessageContent(message_text="👀 Start typing... For example: Yeat")
            )
        ], cache_time=1)
        return

    tracks = await asyncio.to_thread(search_soundcloud, search_text)
    
    if not tracks:
        await query.answer([
            InlineQueryResultArticle(
                id="not_found",
                title="⛔️ Nothing found",
                description="Try changing your query",
                input_message_content=InputTextMessageContent(message_text="⛔️ Nothing found. Try changing your query.")
            )
        ], cache_time=1)
        return

    results = []
    
    for i, track in enumerate(tracks):
        track_id = str(track.get("id") or i)
        
        title = track.get("title", "Unknown")
        artist = track.get("uploader", "Unknown Artist")
        duration_str = format_duration(track.get("duration"))
        
        raw_thumb = track.get("thumbnails", [{}])[-1].get("url", "")
        safe_thumb = raw_thumb.replace("t500x500", "t300x300").replace("crop", "t300x300").replace("large", "t300x300").replace("original", "t300x300") if raw_thumb else None
        
        url_cache[track_id] = (track.get("url"), title, artist)
        
        results.append(InlineQueryResultArticle(
            id=track_id,
            title=title, 
            description=f"{artist} ({duration_str})",
            thumbnail_url=safe_thumb,
            input_message_content=InputTextMessageContent(
                message_text=f"⏳ <b>{artist} — {title}</b>",
                parse_mode="HTML"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ InlineKeyboardButton(text="Downloading...", callback_data="loading") ]])
        ))
        
    await query.answer(results, cache_time=30)

@dp.chosen_inline_result()
async def handle_choice(chosen_result: ChosenInlineResult):
    track_id = chosen_result.result_id
    inline_id = chosen_result.inline_message_id
    cached_data = url_cache.get(track_id)
    
    if not cached_data or not inline_id:
        return

    url, title, artist = cached_data
    loop = asyncio.get_running_loop()
    
    try:
        await bot.edit_message_text(
            inline_message_id=inline_id,
            text=f"🔄 <b>{artist} — {title}</b> <i>Connecting...</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ InlineKeyboardButton(text="Connecting...", callback_data="loading") ]])
        )
    except:
        pass

    try:
        info = await asyncio.to_thread(download_track, url, inline_id, title, artist, loop)
        
        try:
            await bot.edit_message_text(
                inline_message_id=inline_id,
                text=f"☁️ <b>{artist} — {title}</b> <i>Uploading: 67%</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ InlineKeyboardButton(text="Uploading...", callback_data="loading") ]])
            )
        except:
            pass

        thumb_url = info.get("thumbnail")
        thumb_path = None
        
        if thumb_url:
            thumb_path = f"downloads/{track_id}_cover.jpg"
            try:
                timeout = aiohttp.ClientTimeout(total=5) 
                async with aiohttp.ClientSession(timeout=timeout) as client:
                    async with client.get(thumb_url) as resp:
                        if resp.status == 200:
                            with open(thumb_path, "wb") as f:
                                f.write(await resp.read())
                        else:
                            thumb_path = None
            except Exception:
                thumb_path = None
        
        temp_msg = await bot.send_audio(
            chat_id=5500221743, 
            audio=FSInputFile(info["path"], chunk_size=1024 * 1024),
            title=info["title"],
            performer=info["artist"],
            duration=info["duration"],
            thumbnail=FSInputFile(thumb_path) if thumb_path and os.path.exists(thumb_path) else None,
            request_timeout=60
        )
        
        file_id = temp_msg.audio.file_id
        
        await bot.edit_message_media(
            inline_message_id=inline_id,
            media=InputMediaAudio(media=file_id)
        )
        
        await temp_msg.delete()
        
        if os.path.exists(info["path"]):
            os.remove(info["path"])
            
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
    except Exception as e:
        print(e)
        
        try:
            await bot.edit_message_text(inline_message_id=inline_id, text=f"⛔️ <b>{artist} — {title}</b> <i>Failed.. Try again</i>", parse_mode="HTML")
        except:
            pass

async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())