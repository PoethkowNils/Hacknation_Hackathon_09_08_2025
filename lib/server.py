import asyncio
import base64
import json
import sys
import websockets
import ssl
import os

def sts_connect():
    # You can run export DEEPGRAM_API_KEY="your key" in your terminal to set your API key.
    api_key = os.getenv('DEEPGRAM_API_KEY')
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY environment variable is not set")

    sts_ws = websockets.connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        subprotocols=["token", api_key]
    )
    return sts_ws

async def twilio_handler(twilio_ws):
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async with sts_connect() as sts_ws:
        config_message = {
            "type": "Settings",
            "audio": {
                "input": {
                    "encoding": "mulaw",
                    "sample_rate": 8000,
                },
                "output": {
                    "encoding": "mulaw",
                    "sample_rate": 8000,
                    "container": "none",
                },
            },
            "agent": {
                "language": "en",
                "listen": {
                    "provider": {
                        "type": "deepgram",
                        "model": "nova-3",
                        "keyterms": ["hello", "goodbye"]
                    }
                },
                "think": {
                    "provider": {
                        "type": "open_ai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.7
                    },
                    "prompt": (
                        "You are a silent fraud detection assistant for a live phone call. "
                        "Your task is to analyze the user's speech for signs of fraud. "
                        "You must evaluate two things:\n"
                        "1.  **Content Fraud**: Does the user's language exhibit scam tactics? (e.g., creating urgency, requesting sensitive information like passwords or social security numbers, impersonating authority, threats).\n"
                        "2.  **Vocal Anomalies**: Based on the transcription's timing and flow, are there signs of a non-human or deepfaked voice? (e.g., unnatural pacing, odd hesitations, monotonic speech, lack of emotion).\n\n"
                        "Respond ONLY with a JSON object. Do not add any other text. The JSON should have the following structure:\n"
                        "{\n"
                        '  "is_fraudulent": boolean,\n'
                        '  "fraud_type": "content" | "vocal" | "none" | "both",\n'
                        '  "confidence": "low" | "medium" | "high",\n'
                        '  "reasoning": "A brief explanation of your findings."\n'
                        "}\n"
                        "If no fraud is detected, set is_fraudulent to false and fraud_type to 'none'."
                    )
                },
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": "aura-2-thalia-en"
                    }
                },
                "greeting": ""
            }
        }
        await sts_ws.send(json.dumps(config_message))

        async def sts_sender(sts_ws):
            print("sts_sender started")
            while True:
                chunk = await audio_queue.get()
                await sts_ws.send(chunk)
                audio_queue.task_done()  # Wichtig: Signal, dass die Aufgabe erledigt ist

        async def sts_receiver(sts_ws):
            print("sts_receiver started")
            streamsid = await streamsid_queue.get()
            async for message in sts_ws:
                if isinstance(message, str):
                    print(message)
                    decoded = json.loads(message)
                    if decoded['type'] == 'UserStartedSpeaking':
                        clear_message = {
                            "event": "clear",
                            "streamSid": streamsid
                        }
                        await twilio_ws.send(json.dumps(clear_message))

                    elif decoded['type'] == 'assistant':
                        print("\n--- FRAUD ANALYSIS ---")
                        try:
                            analysis = json.loads(decoded.get('prompt_response', '{}'))
                            is_fraud = analysis.get('is_fraudulent', False)
                            fraud_type = analysis.get('fraud_type', 'none')
                            reasoning = analysis.get('reasoning', 'No analysis provided.')

                            if is_fraud:
                                print(f"🚨 ALERT: Potential Fraud Detected!")
                                print(f"   Type: {fraud_type.upper()}")
                                print(f"   Reasoning: {reasoning}")
                            else:
                                print("✅ Call appears normal.")
                                print(f"   Analysis: {reasoning}")
                        except json.JSONDecodeError:
                            print("⚠️ Could not parse agent's analysis.")
                            print(f"Raw Response: {decoded.get('prompt_response')}")
                        print("------------------------\n")
                    continue

                raw_mulaw = message
                media_message = {
                    "event": "media",
                    "streamSid": streamsid,
                    "media": {"payload": base64.b64encode(raw_mulaw).decode("ascii")},
                }
                await twilio_ws.send(json.dumps(media_message))

        async def twilio_receiver(twilio_ws):
            print("twilio_receiver started")
            BUFFER_SIZE = 20 * 160
            inbuffer = bytearray(b"")
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
                        audio_queue.put_nowait(chunk)
                        inbuffer = inbuffer[BUFFER_SIZE:]
                except json.JSONDecodeError:
                    print("Received a non-JSON message, ignoring.")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print("Twilio connection closed.")
                    break

            print("twilio_receiver finished, signaling sts_sender to stop.")
            audio_queue.put_nowait(None)  # Signal, dass kein Audio mehr kommt

        await asyncio.gather(
            sts_sender(sts_ws),
            sts_receiver(sts_ws),
            twilio_receiver(twilio_ws),
        )

        await twilio_ws.close()

async def router(websocket):
    #print(f"Incoming connection on path: {path}")
    #if path == "/twilio":
    print("Starting Twilio handler")
    await twilio_handler(websocket)

# Nachher
async def main():
    print("Starting WebSocket server...")
    # websockets.serve gibt ein AsyncContextManager-Objekt zurück.
    # 'async with' startet den Server und sorgt dafür, dass er auch wieder sauber beendet wird.
    async with websockets.serve(router, "localhost", 5000):
        print("Server is now running on ws://localhost:5000")
        # Dieser Befehl hält das Programm am Laufen,
        # bis ein externes Signal (z. B. Strg+C) den Server stoppt.
        await asyncio.Future()  # Warte unbegrenzt, bis der Task beendet wird.

if __name__ == "__main__":
    try:
        # asyncio.run() startet eine neue Event-Loop und führt die 'main()'-Funktion aus.
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped by user.")
    sys.exit(0)