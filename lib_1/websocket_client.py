# server.py - Runs on localhost:5000, relays to Deepgram

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
    "?encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&diarize=true"           # Diarization!
    "&punctuate=true"        
    "&model=nova-2"           # best model
)

# Track active client and Deepgram connection
clients = set()


async def relay_to_deepgram(websocket_client):
    """Relay audio from client to Deepgram and send back transcripts."""
    print("Connecting to Deepgram ...")

    async with websockets.connect(
        DEEPGRAM_URL,
        subprotocols=["token", DEEPGRAM_API_KEY]
    ) as dg_ws:
        print("Connected to Deepgram!")

        # Forward transcription back to client
        async def receive_transcription():
            async for msg in dg_ws:
                try:
                    result = json.loads(msg)
                    if result.get("type") == "PartialTranscript":
                        transcript = result["channel"]["alternatives"][0]["transcript"]
                        # Extract speaker if available
                        speaker = "Unknown"
                        if "speakers" in result["channel"]["alternatives"][0]:
                            speaker = result["channel"]["alternatives"][0]["speakers"][0].get("label", "Unknown")
                        # Send to client
                        print(transcript)
                        await websocket_client.send(
                            json.dumps({
                                "transcript": transcript,
                                "speaker": speaker,
                                "is_final": False
                            })
                        )
                    elif result.get("type") == "FinalTranscript":
                        transcript = result["channel"]["alternatives"][0]["transcript"]
                        speaker = "Unknown"
                        if "speakers" in result["channel"]["alternatives"][0]:
                            speaker = result["channel"]["alternatives"][0]["speakers"][0].get("label", "Unknown")

                        print(transcript)
                        await websocket_client.send(
                            json.dumps({
                                "transcript": transcript,
                                "speaker": speaker,
                                "is_final": True
                            })
                        )
                except Exception as e:
                    print("Error processing Deepgram result:", e)

        # Forward audio from client to Deepgram
        async def forward_audio():
            try:
                async for message in websocket_client:
                    # Send raw audio bytes to Deepgram
                    await dg_ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                print("Client disconnected.")

        # Run both directions
        await asyncio.gather(forward_audio(), receive_transcription())


async def handler(websocket, path):
    """Handle new client connection."""
    print(f"Client connected: {websocket.remote_address}")
    clients.add(websocket)
    try:
        await relay_to_deepgram(websocket)
    except websockets.exceptions.ConnectionClosed:
        print("Client connection closed.")
    finally:
        clients.remove(websocket)


# Start server
start_server = websockets.serve(handler, "localhost", 5000)
print("Server listening on ws://localhost:5000")



if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()