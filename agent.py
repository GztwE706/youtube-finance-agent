"""
YouTube 財經特工 — 自動監控 + Whisper 逐字稿 + GPT 摘要 + LINE 通知
"""

import os
import sys
import requests
from openai import OpenAI
from yt_dlp import YoutubeDL

LINE_TOKEN   = os.environ["LINE_TOKEN"]
OPENAI_KEY   = os.environ["OPENAI_API_KEY"]
CHANNEL_URL  = os.environ["CHANNEL_URL"]
COOKIE_FILE  = "youtube_cookies.txt"
HISTORY_FILE = "history.txt"
AUDIO_DIR    = "/tmp/audio"
WHISPER_MODEL = "base"

client = OpenAI(api_key=OPENAI_KEY)

def get_latest_video():
    ydl_opts = {"cookiefile": COOKIE_FILE, "extract_flat": True, "playlistend": 3, "quiet": True}
    with YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(CHANNEL_URL, download=False)
        entries = result.get("entries", [])
        return [(e["id"], e.get("title", "未命名")) for e in entries if e]

def download_audio(video_id):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "cookiefile": COOKIE_FILE,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(AUDIO_DIR, f"{video_id}.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "96"}],
        "quiet": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return os.path.join(AUDIO_DIR, f"{video_id}.mp3")

def transcribe(audio_path):
    import whisper
    print("  [Whisper] 載入模型中...")
    model = whisper.load_model(WHISPER_MODEL)
    print("  [Whisper] 開始轉錄...")
    result = model.transcribe(audio_path, language="zh", initial_prompt="以下是台灣繁體中文的財經股市投資分析內容。", fp16=False)
    return result["text"]

def summarize(transcript, title):
    system_prompt = (
        "你是一位專業的台股證券分析師助理。"
        "請將以下財經老師的會員影片逐字稿整理成精簡報告，使用繁體中文。\n"
        "格式：\n📈 大盤與市場趨勢：\n🎯 重點追蹤標的：\n⚙️ 操作策略：\n⚠️ 風險提示：\n字數500字以內。"
    )
    if len(transcript) > 12000:
        transcript = transcript[:12000] + "\n[...以下省略...]"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"影片標題：{title}\n\n逐字稿：\n{transcript}"},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    return response.choices[0].message.content

def send_line(message):
    for chunk in [message[i:i+950] for i in range(0, len(message), 950)]:
        requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            data={"message": chunk},
            timeout=10,
        )

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_history(video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")

def main():
    print("=== YouTube 財經特工啟動 ===")
    videos = get_latest_video()
    if not videos:
        print("無法取得影片清單")
        sys.exit(0)

    history = load_history()
    new_count = 0

    for video_id, title in videos:
        if video_id in history:
            print(f"  [跳過] {title}")
            continue

        print(f"  ★ 新影片：{title}")
        new_count += 1
        send_line(f"\n🔔 偵測到新影片！\n📌 {title}\n⏳ AI 處理中，約需 15-25 分鐘...")

        try:
            mp3 = download_audio(video_id)
            transcript = transcribe(mp3)
            summary = summarize(transcript, title)
            send_line(f"\n📊【AI 財經特工報告】\n📌 {title}\n{'─'*20}\n{summary}")
            print("  ✅ 完成！")
            save_history(video_id)
            if os.path.exists(mp3):
                os.remove(mp3)
        except Exception as e:
            send_line(f"\n❌ 處理失敗：{title}\n錯誤：{str(e)[:200]}")

    if new_count == 0:
        print("  本次無新影片。")

if __name__ == "__main__":
    main()
