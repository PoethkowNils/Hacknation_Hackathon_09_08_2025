import asyncio
import base64
import json
import sys
import websockets
import ssl
import os
import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Global queue to send fraud alerts to frontend clients
FRAUD_ALERT_QUEUE = asyncio.Queue()

def sts_connect():
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
        # Send Deepgram Agent configuration
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
                        "keyterms": ["urgent", "password", "verify", "social security", "transfer"]
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
                        "Evaluate two things:\n"
                        "1. **Content Fraud**: Scam tactics like urgency, requesting sensitive info, impersonation.\n"
                        "2. **Vocal Anomalies**: Unnatural pacing, monotone, robotic tone, lack of emotion.\n\n"
                        "Respond ONLY with a JSON object:\n"
                        "{\n"
                        '  "is_fraudulent": boolean,\n'
                        '  "fraud_type": "content" | "vocal" | "none" | "both",\n'
                        '  "confidence": "low" | "medium" | "high",\n'
                        '  "reasoning": "Brief explanation."\n'
                        "}\n"
                        "If no fraud, set is_fraudulent=false, fraud_type='none'."
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
                if chunk == b'':  # End signal
                    break
                await sts_ws.send(chunk)

        async def sts_receiver(sts_ws):
            print("sts_receiver started")
            streamsid = await streamsid_queue.get()

            async for message in sts_ws:
                if isinstance(message, str):
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
                            confidence = analysis.get('confidence', 'low')
                            reasoning = analysis.get('reasoning', 'No analysis.')

                            alert = {
                                "event": "fraud_update",
                                "is_fraudulent": is_fraud,
                                "fraud_type": fraud_type,
                                "confidence": confidence,
                                "reasoning": reasoning,
                                "timestamp": datetime.datetime.now().isoformat()
                            }

                            # Send to frontend
                            await FRAUD_ALERT_QUEUE.put(alert)

                            # Log
                            if is_fraud:
                                print(f"🚨 FRAUD ALERT [{confidence.upper()}]: {fraud_type} → {reasoning}")
                            else:
                                print(f"✅ Safe: {reasoning}")

                        except json.JSONDecodeError:
                            print("⚠️ Failed to parse LLM response:", decoded.get('prompt_response'))
                        print("------------------------\n")
                    continue

                # TTS audio from Deepgram → send to Twilio
                raw_mulaw = message
                media_message = {
                    "event": "media",
                    "streamSid": streamsid,
                    "media": {"payload": base64.b64encode(raw_mulaw).decode("ascii")}
                }
                await twilio_ws.send(json.dumps(media_message))

        async def twilio_receiver(twilio_ws):
            print("twilio_receiver started")
            BUFFER_SIZE = 20 * 160  # 0.4 seconds
            inbuffer = bytearray(b"")

            async for message in twilio_ws:
                try:
                    data = json.loads(message)
                    if data["event"] == "start":
                        print("Received start event, streamSid:", data["start"]["streamSid"])
                        streamsid_queue.put_nowait(data["start"]["streamSid"])
                    elif data["event"] == "connected":
                        continue
                    elif data["event"] == "media":
                        payload = base64.b64decode(data["media"]["payload"])
                        if data["media"]["track"] == "inbound":
                            inbuffer.extend(payload)
                    elif data["event"] == "stop":
                        print("Call stopped.")
                        break

                    # Flush buffer to Deepgram
                    while len(inbuffer) >= BUFFER_SIZE:
                        chunk = inbuffer[:BUFFER_SIZE]
                        audio_queue.put_nowait(chunk)
                        inbuffer = inbuffer[BUFFER_SIZE:]

                except Exception as e:
                    print("Error in twilio_receiver:", e)
                    break

            # Signal end
            audio_queue.put_nowait(b'')

        # Run all tasks
        await asyncio.gather(
            sts_sender(sts_ws),
            sts_receiver(sts_ws),
            twilio_receiver(twilio_ws)
        )

        await twilio_ws.close()

async def client_handler(websocket: websockets.WebSocketServerProtocol):
    """Handles connections from the frontend UI"""
    print("Frontend client connected")
    try:
        while True:
            alert = await FRAUD_ALERT_QUEUE.get()
            await websocket.send(json.dumps(alert))
    except websockets.exceptions.ConnectionClosed:
        print("Frontend client disconnected")

async def router(websocket, path):
    print(f"Incoming connection on path: {path}")
    if path == "/twilio":
        await twilio_handler(websocket)
    elif path == "/client":
        await client_handler(websocket)
    else:
        print(f"Unknown path: {path}")
        await websocket.close()

def main():
    # For production with SSL:
    # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # ssl_context.load_cert_chain('cert.pem', 'key.pem')
    # server = websockets.serve(router, "0.0.0.0", 443, ssl=ssl_context)

    # For local development:
    server = websockets.serve(router, "localhost", 5000)
    print("Server starting on ws://localhost:5000")
    asyncio.get_event_loop().run_until_complete(server)
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        sys.exit(0)