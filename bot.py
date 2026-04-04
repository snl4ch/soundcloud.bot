# Gemini 3.1 Pro

import os
import yt_dlp
import asyncio

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    ChosenInlineResult,
    InputMediaAudio,
    URLInputFile,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

load_dotenv()

bot = Bot(token=os.getenv("TOKEN"))
dp = Dispatcher()

url_cache = {}

def format_duration(seconds) -> str:
    if not seconds:
        return "0:00"
    
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

def search_soundcloud(query: str, limit: int = 10) -> list:
    ydl_opts = {"format": "bestaudio/best", "extract_flat": True, "quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
        return result.get("entries", [])

def download_track(url: str) -> dict:
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "writethumbnail": True, 
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"}, 
        ],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        raw_duration = info.get("duration", 0)
        safe_duration = int(raw_duration) if raw_duration else 0
        
        return {
            "path": f"downloads/{info["id"]}.mp3",
            "title": info.get("title", "Unknown"),
            "artist": info.get("uploader", "Unknown Artist"),
            "duration": safe_duration,
            "thumbnail": info.get("thumbnails", [{}])[-1].get("url") 
        }

@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = "🤓 Msg anywhere <b>@loadsongbot s0Ng nAm3</b> to search ur music"
    
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
                input_message_content=InputTextMessageContent(
                    message_text="👀 Start typing... For example: Yeat"
                )
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
                input_message_content=InputTextMessageContent(
                    message_text="⛔️ Nothing found. Try changing your query."
                )
            )
        ], cache_time=5)
        return

    results = []
    
    for i, track in enumerate(tracks):
        track_id = str(track.get("id") or i)
        url_cache[track_id] = track.get("url")
        
        title = track.get("title", "Unknown")
        artist = track.get("uploader", "Unknown Artist")
        duration_str = format_duration(track.get("duration"))
        thumbnail = track.get("thumbnails", [{}])[-1].get("url")
        
        results.append(InlineQueryResultArticle(
            id=track_id,
            title=title, 
            description=f"{artist} ({duration_str})",
            thumbnail_url=thumbnail,
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
    url = url_cache.get(track_id)
    
    if not url or not inline_id:
        return

    try:
        info = await asyncio.to_thread(download_track, url)
        
        thumb_url = info.get("thumbnail")
        thumb_file = URLInputFile(thumb_url) if thumb_url else None
        
        temp_msg = await bot.send_audio(
            chat_id=os.getenv("USER"), 
            audio=FSInputFile(info["path"]),
            title=info["title"],
            performer=info["artist"],
            duration=info["duration"],
            thumbnail=thumb_file
        )
        
        file_id = temp_msg.audio.file_id
        
        await bot.edit_message_media(
            inline_message_id=inline_id,
            media=InputMediaAudio(media=file_id)
        )
        
        await temp_msg.delete()
        if os.path.exists(info["path"]):
            os.remove(info["path"])
            
    except Exception as e:
        print(e)

async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())