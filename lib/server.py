import asyncio
import base64
import json
import websockets
import os
import torch
import sys

from model_loader import get_model, get_device
from anti_spoofing import load_model, anti_spoofing_worker

model = get_model()
device = get_device()

async def twilio_handler(twilio_ws):
    audio_queue = asyncio.Queue()
    spoof_results_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async def twilio_receiver():
        print("twilio_receiver started")
        BUFFER_SIZE = 20 * 160
        inbuffer = bytearray()
        async for message in twilio_ws:
            try:
                data = json.loads(message)
                if data["event"] == "start":
                    print("got our streamsid")
                    start = data["start"]
                    streamsid = start["streamSid"]
                    streamsid_queue.put_nowait(streamsid)
                elif data["event"] == "connected":
                    continue
                elif data["event"] == "media":
                    media = data["media"]
                    if media["track"] == "inbound":
                        chunk = base64.b64decode(media["payload"])
                        inbuffer.extend(chunk)
                elif data["event"] == "stop":
                    break

                while len(inbuffer) >= BUFFER_SIZE:
                    chunk = inbuffer[:BUFFER_SIZE]
                    await audio_queue.put(chunk)
                    inbuffer = inbuffer[BUFFER_SIZE:]
            except json.JSONDecodeError:
                print("Received a non-JSON message, ignoring.")
                continue
            except websockets.exceptions.ConnectionClosed:
                print("Twilio connection closed.")
                break

        print("twilio_receiver finished, signaling anti-spoofing worker to stop.")
        await audio_queue.put(None)  # Signal, dass kein Audio mehr kommt

    async def run_anti_spoofing():
        print("server started anti-spoofing worker")
        await anti_spoofing_worker(audio_queue, spoof_results_queue, model)

    # Nur die zwei Tasks starten, keine Deepgram-Verbindung mehr
    await asyncio.gather(
        twilio_receiver(),
        run_anti_spoofing(),
    )

    await twilio_ws.close()

async def router(websocket):
    print("Starting Twilio handler")
    await twilio_handler(websocket)

async def main():
    print("Starting WebSocket server...")
    async with websockets.serve(router, "localhost", 5000):
        print("Server is now running on ws://localhost:5000")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped by user.")
    sys.exit(0)
