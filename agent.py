"""
YouTube 財經特工 — 自動監控 + Whisper 逐字稿 + GPT 摘要 + Gmail 通知
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
from yt_dlp import YoutubeDL

GMAIL_USER   = os.environ["GMAIL_USER"]
GMAIL_PASS   = os.environ["GMAIL_PASS"]
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
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(AUDIO_DIR, f"{video_id}.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "96"}],
        "geo_bypass": True,
        "geo_bypass_country": "TW",
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

def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)
    print("  ✅ Email 已發送！")

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

        try:
            mp3 = download_audio(video_id)
            transcript = transcribe(mp3)
            summary = summarize(transcript, title)
            send_email(
                subject=f"📊 AI財經特工報告：{title}",
                body=f"影片標題：{title}\n\n{'─'*30}\n\n{summary}"
            )
            save_history(video_id)
            if os.path.exists(mp3):
                os.remove(mp3)
        except Exception as e:
            send_email(subject=f"❌ 處理失敗：{title}", body=f"錯誤：{str(e)[:500]}")

    if new_count == 0:
        print("  本次無新影片。")

if __name__ == "__main__":
    main()
