"""Synthetic example code for the scanner (not meant to run)."""
import anthropic
import openai

claude = anthropic.Anthropic()
reply = claude.messages.create(model="claude-3-5-haiku-20241022", max_tokens=512,
                               messages=[{"role": "user", "content": "hi"}])

oai = openai.OpenAI()
with open("call.mp3", "rb") as f:
    text = oai.audio.transcriptions.create(model="whisper-1", file=f)

summary = oai.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": text.text}])
