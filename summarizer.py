import time 
import anthropic
import argparse
import json
import os
import re
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from rich.console import Console
from rich.panel import Panel

console =Console() # bu yazdıma nesnemiz her yerde kullanırız bir kere yazarız 

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def get_video_id(url):
    """YouTube URL'sinden video ID'sini çıkarır."""
     # Shell escape karakterlerini temizle (zsh url-quote-magic)
    url = url.replace("\\", "")
    match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None

def get_transcript(video_id):
    """Video ID'sinden transkripti tek string olarak döndürür."""
    ytt_api = YouTubeTranscriptApi()
    fetched_transcript = ytt_api.fetch(video_id, languages=['tr', 'en'])
    return " ".join([snippet.text for snippet in fetched_transcript])


def analyze(transcript, max_retries=3):
    """Transkripti Claude'a yollar, hata durumunda 3 kez tekrar dener."""
    prompt = f"""Aşağıdaki YouTube video transkriptini analiz et ve TAM olarak şu JSON formatında cevap ver, başka hiçbir şey yazma:

{{
  "ozet": "3-5 cümlelik özet, Türkçe",
  "ana_noktalar": ["nokta 1", "nokta 2", "nokta 3"],
  "en_iyi_alintilar": ["transkriptten gerçek alıntı 1", "alıntı 2"],
  "linkedin_paylasim": "100-200 kelimelik Türkçe LinkedIn paylaşımı"
}}

Transkript:
{transcript}"""

    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return msg.content[0].text
        
        except anthropic.APIStatusError as e:
            # 5xx (sunucu) ve 429 (rate limit) hatalarında tekrar dene
            if e.status_code in [429, 500, 502, 503, 529]:
                wait = 2 ** attempt  # 1, 2, 4 saniye bekle
                console.print(f"[yellow]API hatası ({e.status_code}), {wait}s bekleniyor... ({attempt+1}/{max_retries})[/yellow]")
                time.sleep(wait)
            else:
                raise  # Diğer hatalarda direkt çık
    
    raise Exception(f"{max_retries} denemeden sonra hâlâ başarısız")


def parse_response(text):
    """Claude'un cevabından JSON'u çıkar ve dict'e çevir."""
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


# --- Test ---
parser = argparse.ArgumentParser(description="YouTube videolarını AI ile özetler")
parser.add_argument("url", help="Özetlenecek YouTube video URL'si")
args = parser.parse_args()

url = args.url
video_id = get_video_id(url)
if video_id is None:
    console.print("[bold red]Hata: URL'den video ID çıkarılamadı. Doğru YouTube URL'si verdiğine emin ol.[/bold red]")
    exit(1)
print(f"Video ID: {video_id}")

transcript = get_transcript(video_id)
print(f"Transkript ({len(transcript)} karakter):\n")

with console.status("[bold cyan]Claude analiz ediyor...", spinner="dots"):
    raw = analyze(transcript)

result = parse_response(raw)

console.print(Panel(result["ozet"], title="📝 Özet", border_style="cyan"))

ana_noktalar_text = "\n".join([f"• {nokta}" for nokta in result["ana_noktalar"]])
console.print(Panel(ana_noktalar_text, title="🎯 Ana Noktalar", border_style="green"))

alintilar_text = "\n".join([f"→ {alinti}" for alinti in result["en_iyi_alintilar"]])
console.print(Panel(alintilar_text, title="💬 En İyi Alıntılar", border_style="yellow"))

console.print(Panel(result["linkedin_paylasim"], title="📱 LinkedIn Paylaşımı", border_style="magenta"))