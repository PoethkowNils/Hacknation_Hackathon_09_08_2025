import asyncio
import websockets
import json
import os
import torch
import numpy as np
import torchaudio

from anti_spoofing import load_model  # Dein echtes Modell laden

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    raise RuntimeError("Please set DEEPGRAM_API_KEY environment variable.")

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&diarize=true"
    "&punctuate=true"
    "&model=nova-2"
)

device = "cuda" if torch.cuda.is_available() else "cpu"

# Lade echtes Modell
anti_spoofing_model = load_model()
anti_spoofing_model.to(device)
anti_spoofing_model.eval()

resampler = torchaudio.transforms.Resample(orig_freq=8000, new_freq=16000).to(device)

def resample_audio(audio_chunk):
    audio_np = np.frombuffer(audio_chunk, dtype=np.uint8).astype(np.float32) - 128
    audio_tensor = torch.from_numpy(audio_np).to(device)

    audio_resampled = resampler(audio_tensor)
    audio_resampled /= torch.max(torch.abs(audio_resampled)) + 1e-9
    return audio_resampled

async def anti_spoofing_worker(audio_queue, spoof_results_queue):
    print("Anti-spoofing worker started.")
    SPOOFING_WINDOW_SIZE_SAMPLES = 16000 * 2  # 2 Sekunden Fenster
    spoofing_buffer = []

    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break

        resampled_chunk = resample_audio(chunk)
        spoofing_buffer.append(resampled_chunk)

        current_buffer_size = sum(c.size(0) for c in spoofing_buffer)
        if current_buffer_size >= SPOOFING_WINDOW_SIZE_SAMPLES:

            print(f"resampled_chunk shape: {resampled_chunk.shape}")
            print(f"buffer elements shapes before cat: {[c.shape for c in spoofing_buffer]}")

            audio_tensor = torch.cat(spoofing_buffer, dim=0)  # Shape: [32000]
            print(f"audio_tensor shape after cat: {audio_tensor.shape}")

            audio_window = audio_tensor.view(1, 1, -1)  # Shape: [1, 1, 32000]
            print(f"audio_window shape after reshape: {audio_window.shape}")

            audio_window = torch.cat(spoofing_buffer, dim=0).unsqueeze(0)  # Batch-Dim hinzufügen
            with torch.no_grad():
                print("calling anti-spoofing model...")
                output = anti_spoofing_model(audio_window)
                print(f"Model output type: {type(output)}")
                print(f"Model output: {output}")
                if isinstance(output, tuple):
                    print(f"Output is a tuple with {len(output)} elements:")
                    for i, elem in enumerate(output):
                        print(f"Element {i} type: {type(elem)}, value: {elem}, shape: {elem.shape if hasattr(elem, 'shape') else 'N/A'}")
                score = output[0].item() if isinstance(output, tuple) else output.item()  # Vorläufige Annahme
                print(f"Extracted score: {score}")
                await spoof_results_queue.put(score)
            spoofing_buffer = []

        audio_queue.task_done()
    print("Anti-spoofing worker finished.")


async def relay_to_deepgram(websocket_client):
    print("Connecting to Deepgram ...")

    audio_queue = asyncio.Queue()
    spoof_results_queue = asyncio.Queue()

    async with websockets.connect(
            DEEPGRAM_URL,
            subprotocols=["token", DEEPGRAM_API_KEY]
    ) as dg_ws:
        print("Connected to Deepgram!")

        async def receive_transcription():
            async for msg in dg_ws:
                try:
                    result = json.loads(msg)

                    if result.get("type") == "PartialTranscript":
                        transcript = result["channel"]["alternatives"][0]["transcript"]
                        speaker = result["channel"]["alternatives"][0].get("speakers", [{}])[0].get("label", "Unknown")
                        await websocket_client.send(
                            json.dumps({
                                "transcript": transcript,
                                "speaker": speaker,
                                "is_final": False,
                                "is_spoof": False
                            })
                        )
                    elif result.get("type") == "FinalTranscript":
                        transcript = result["channel"]["alternatives"][0]["transcript"]
                        speaker = result["channel"]["alternatives"][0].get("speakers", [{}])[0].get("label", "Unknown")

                        # Spoofing Score abfragen (non-blocking)
                        spoof_score = None
                        is_spoof = False
                        try:
                            spoof_score = spoof_results_queue.get_nowait()
                            if spoof_score > 0.8:  # Threshold anpassen
                                is_spoof = True
                            print(f"Final Transcript: {transcript} (Speaker: {speaker}) - Spoof Score: {spoof_score:.3f}, Is Spoof: {is_spoof}")
                        except asyncio.QueueEmpty:
                            print(f"Final Transcript: {transcript} (Speaker: {speaker}) - No spoofing score available.")

                        await websocket_client.send(
                            json.dumps({
                                "transcript": transcript,
                                "speaker": speaker,
                                "is_final": True,
                                "is_spoof": is_spoof
                            })
                        )
                except Exception as e:
                    print(f"Error processing Deepgram result: {e}")

        async def forward_audio():
            try:
                async for message in websocket_client:
                    await audio_queue.put(message)  # Für Spoofing Worker
                    await dg_ws.send(message)       # An Deepgram weiterleiten
            except websockets.exceptions.ConnectionClosed:
                print("Client disconnected.")
                await audio_queue.put(None)  # Signal Ende Stream

        await asyncio.gather(
            forward_audio(),
            receive_transcription(),
            anti_spoofing_worker(audio_queue, spoof_results_queue)
        )


async def handler(websocket, path):
    print(f"Client connected: {websocket.remote_address}")
    try:
        await relay_to_deepgram(websocket)
    except websockets.exceptions.ConnectionClosed:
        print("Client connection closed.")


if __name__ == "__main__":
    start_server = websockets.serve(handler, "localhost", 5000)
    print("Server listening on ws://localhost:5000")
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
