# deepgram_stream.py

import asyncio
import json
import websockets
import pyaudio
import os

# Load API key from environment variable
# Run: export DEEPGRAM_API_KEY='your-key-here' before running script
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Please set DEEPGRAM_API_KEY environment variable.")

# Audio settings
FORMAT = pyaudio.paInt16        # 16-bit int sampling
CHANNELS = 1                    # Mono
RATE = 16000                    # 16kHz sample rate
CHUNK = 1024                    # 64ms chunks (1024 / 16000 ≈ 0.064s)

# Deepgram WebSocket URL with query params
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16"
    "&sample_rate=16000"
    "&channels=1"
    "&diarize=true"              # Enable speaker diarization
    "&punctuate=true"            # Add punctuation
    "&model=nova-2"              # Best model (as of 2025)
)


async def stream_audio():
    print("🎙️ Connecting to Deepgram...")

    async with websockets.connect(
        DEEPGRAM_URL,
        additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    ) as ws:
        print("🟢 Connected to Deepgram! Speak now...\n")

        async def mic_listener():
            """Capture audio from mic and stream to Deepgram."""
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            try:
                while True:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    await ws.send(data)
                    await asyncio.sleep(0.001)  # Prevent blocking
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket closed during send.")
            finally:
                stream.stop_stream()
                stream.close()
                audio.terminate()

        async def response_listener():
            """Receive transcription results from Deepgram."""
            try:
                async for msg in ws:
                    try:
                        result = json.loads(msg)
                        if result.get("type") == "PartialTranscript":
                            transcript = result["channel"]["alternatives"][0]["transcript"]
                            # Get speaker if available
                            if "speakers" in result.get("channel", {}).get("alternatives", [{}])[0]:
                                speaker = result["channel"]["alternatives"][0]["speakers"][0].get("label", "Unknown")
                                print(f"🟡 [{speaker}]: {transcript}", end="\r")
                            else:
                                print(f"🟡 {transcript}", end="\r")

                        elif result.get("type") == "FinalTranscript":
                            transcript = result["channel"]["alternatives"][0]["transcript"]
                            if "speakers" in result.get("channel", {}).get("alternatives", [{}])[0]:
                                speaker = result["channel"]["alternatives"][0]["speakers"][0].get("label", "Unknown")
                                print(f"\n✅ [{speaker}]: {transcript}")
                            else:
                                print(f"\n✅ {transcript}")

                    except (KeyError, IndexError) as e:
                        print("Malformed transcript:", result)
            except websockets.exceptions.ConnectionClosed:
                print("Connection to Deepgram closed.")

        # Run both tasks concurrently
        await asyncio.gather(mic_listener(), response_listener())


# Run the stream
if __name__ == "__main__":
    asyncio.run(stream_audio())