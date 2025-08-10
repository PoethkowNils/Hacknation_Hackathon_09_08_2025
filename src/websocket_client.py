# server.py - Runs on localhost:5005, relays to Deepgram

import asyncio
import websockets
import json
import os

# Load Deepgram API key
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Please set DEEPGRAM_API_KEY environment variable.")

# Deepgram WebSocket URL with options
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16"
    "&sample_rate=16000"
    "&channels=1"
    "&diarize=true"
    "&punctuate=true"
    "&model=nova-2"
)

# Track active client and Deepgram connection
clients = set()


async def relay_to_deepgram(websocket_client):
    """Relay audio from client to Deepgram and send back transcripts."""
    print("SERVER: Connecting to Deepgram... 🔄")
    print(DEEPGRAM_URL)
    print(DEEPGRAM_API_KEY)

    try:
        async with websockets.connect(
                DEEPGRAM_URL,
                additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        ) as dg_ws:
            print("SERVER: Connected to Deepgram! ✅")

            # Forward transcription back to client
            async def receive_transcription():
                print("SERVER: Listening for transcriptions from Deepgram... 🎤")
                try:
                    async for msg in dg_ws:
                        result = json.loads(msg)
                        transcript_type = result.get("type")
                        if transcript_type in ["PartialTranscript", "FinalTranscript"]:
                            transcript = result["channel"]["alternatives"][0]["transcript"]
                            speaker = "Unknown"
                            if "speakers" in result["channel"]["alternatives"][0] and result["channel"]["alternatives"][0]["speakers"]:
                                speaker = result["channel"]["alternatives"][0]["speakers"][0].get("label", "Unknown")

                            print(f"SERVER: Received {transcript_type} from Deepgram for speaker {speaker}: {transcript}")
                            await websocket_client.send(
                                json.dumps({
                                    "transcript": transcript,
                                    "speaker": speaker,
                                    "is_final": (transcript_type == "FinalTranscript")
                                })
                            )
                            if transcript_type == "FinalTranscript":
                                print("SERVER: Sent final transcription back to client. 🔊")
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"SERVER: Deepgram-Verbindung wurde geschlossen. Code: {e.code}, Grund: {e.reason}")

                except Exception as e:
                    print("SERVER: Error processing Deepgram result:", e)

            # Forward audio from client to Deepgram
            async def forward_audio():
                #print("SERVER: Forwarding audio from client to Deepgram... 🎤")
                try:
                    async for message in websocket_client:
                        #print(f"SERVER: Forwarding audio chunk of size {len(message)} to Deepgram.")
                        await dg_ws.send(message)
                except websockets.exceptions.ConnectionClosed:
                    print("SERVER: Client disconnected.")

            # Run both directions
            await asyncio.gather(forward_audio(), receive_transcription())
    except Exception as e:
        print(f"SERVER: Failed to connect to Deepgram: {e}")


async def handler(websocket):
    """Handle new client connection."""
    print(f"SERVER: Client connected: {websocket.remote_address} 👋")
    clients.add(websocket)
    try:
        await relay_to_deepgram(websocket)
    except websockets.exceptions.ConnectionClosed:
        print("SERVER: Client connection closed.")
    finally:
        print(f"SERVER: Client disconnected: {websocket.remote_address} ❌")
        clients.remove(websocket)


# Start server
async def main():
    print("SERVER: Starte den WebSocket-Server...")
    async with websockets.serve(handler, "localhost", 5005):
        print("SERVER: Server lauscht auf: ws://localhost:5005 🎧")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())