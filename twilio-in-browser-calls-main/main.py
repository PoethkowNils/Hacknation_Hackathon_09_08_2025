#!/usr/bin/env python3
"""
Combined Flask + Fraud WebSocket server.

- Flask serves:
  - '/' -> your frontend (templates/static as you already have)
  - '/token' -> Twilio access token (JSON)
  - '/handle_calls' -> TwiML for incoming/outgoing calls

- WebSocket server (async) listens on port 5000 and exposes:
  - /twilio -> receives Twilio Media Streams, forwards audio to Deepgram + LLM,
               returns TTS media to Twilio, and posts fraud alerts
  - /client -> frontend clients connect here to receive realtime fraud alerts

Make sure your .env contains:
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_API_KEY_SID,
TWILIO_API_KEY_SECRET, TWIML_APP_SID, TWILIO_NUMBER, DEEPGRAM_API_KEY
"""
import asyncio
import base64
import json
import sys
import websockets
import ssl
import os
import datetime
import threading
import pprint as p

from flask import Flask, render_template, jsonify, request
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Dial

from dotenv import load_dotenv
load_dotenv()

# ---- Twilio / Flask config (same as your main.py) ----
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
api_key = os.environ.get('TWILIO_API_KEY_SID')
api_key_secret = os.environ.get('TWILIO_API_KEY_SECRET')
twiml_app_sid = os.environ.get('TWIML_APP_SID')
twilio_number = os.environ.get('TWILIO_NUMBER')

# Validate minimal env
if not all([account_sid, api_key, api_key_secret, twiml_app_sid, twilio_number]):
    print("Warning: Missing at least one Twilio env var. Make sure .env is set.", file=sys.stderr)

app = Flask(__name__)

@app.route('/')
def home():
    # you said you already have templates/static — keep using them
    return render_template('home.html', title="In browser calls")

@app.route('/token', methods=['GET'])
def get_token():
    identity = twilio_number
    outgoing_application_sid = twiml_app_sid

    access_token = AccessToken(account_sid, api_key, api_key_secret, identity=identity)

    voice_grant = VoiceGrant(
        outgoing_application_sid=outgoing_application_sid,
        incoming_allow=True,
    )
    access_token.add_grant(voice_grant)

    # modern AccessToken.to_jwt() returns str; don't decode
    response = jsonify({'token': access_token.to_jwt(), 'identity': identity})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/handle_calls', methods=['POST'])
def handle_calls():
    p.pprint(request.form)
    response = VoiceResponse()
    dial = Dial(callerId=twilio_number)

    if 'To' in request.form and request.form['To'] != twilio_number:
        print('outbound call')
        dial.number(request.form['To'])
    else:
        print('incoming call')
        caller = request.form.get('Caller', twilio_number)
        dial = Dial(callerId=caller)
        dial.client(twilio_number)

    response.append(dial)
    # return TwiML
    return str(response)

# ---- Fraud detection WebSocket server (mostly server.py) ----

# Global queue to send fraud alerts to frontend clients
FRAUD_ALERT_QUEUE = None  

def sts_connect():
    api_key = os.getenv('DEEPGRAM_API_KEY')
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY environment variable is not set")

    # This mirrors your original: subprotocols list contains token and key
    sts_ws = websockets.connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        subprotocols=["token", api_key]
    )
    return sts_ws

async def twilio_handler(twilio_ws: websockets.WebSocketServerProtocol):
    """
    Handles a Twilio media stream connection.
    Sends audio chunks to Deepgram agent and receives:
      - assistant (fraud analysis JSON) -> convert into alert -> push to FRAUD_ALERT_QUEUE
      - TTS audio from Deepgram -> send back as Twilio media messages
    """
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async with sts_connect() as sts_ws:
        # Send Deepgram Agent configuration (kept from original)
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
                        '  \"is_fraudulent\": boolean,\n'
                        '  \"fraud_type\": \"content\" | \"vocal\" | \"none\" | \"both\",\n'
                        '  \"confidence\": \"low\" | \"medium\" | \"high\",\n'
                        '  \"reasoning\": \"Brief explanation.\"\n'
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
                # Deepgram expects raw bytes. websockets send can accept bytes.
                await sts_ws.send(chunk)

        async def sts_receiver(sts_ws):
            print("sts_receiver started")
            streamsid = await streamsid_queue.get()

            async for message in sts_ws:
                if isinstance(message, str):
                    # text message from Deepgram agent
                    decoded = json.loads(message)
                    if decoded.get('type') == 'UserStartedSpeaking':
                        clear_message = {
                            "event": "clear",
                            "streamSid": streamsid
                        }
                        await twilio_ws.send(json.dumps(clear_message))
                    elif decoded.get('type') == 'assistant':
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

                # Non-text payload - TTS audio bytes from Deepgram
                raw_mulaw = message  # bytes
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
                    if data.get("event") == "start":
                        print("Received start event, streamSid:", data["start"]["streamSid"])
                        await streamsid_queue.put(data["start"]["streamSid"])
                    elif data.get("event") == "connected":
                        continue
                    elif data.get("event") == "media":
                        payload = base64.b64decode(data["media"]["payload"])
                        if data["media"].get("track") == "inbound":
                            inbuffer.extend(payload)
                    elif data.get("event") == "stop":
                        print("Call stopped.")
                        break

                    # Flush buffer to Deepgram in consistent chunks
                    while len(inbuffer) >= BUFFER_SIZE:
                        chunk = bytes(inbuffer[:BUFFER_SIZE])
                        await audio_queue.put(chunk)
                        inbuffer = inbuffer[BUFFER_SIZE:]

                except Exception as e:
                    print("Error in twilio_receiver:", e)
                    break

            # Signal end
            await audio_queue.put(b'')

        # Run all three coroutines concurrently
        await asyncio.gather(
            sts_sender(sts_ws),
            sts_receiver(sts_ws),
            twilio_receiver(twilio_ws)
        )

        await twilio_ws.close()

async def client_handler(websocket: websockets.WebSocketServerProtocol):
    """Handles connections from the frontend UI, pushing fraud alerts from the shared queue."""
    print("Frontend client connected")
    try:
        while True:
            alert = await FRAUD_ALERT_QUEUE.get()
            await websocket.send(json.dumps(alert))
    except websockets.exceptions.ConnectionClosed:
        print("Frontend client disconnected")

async def router(websocket: websockets.WebSocketServerProtocol, path: str):
    """
    Route connections based on path:
      - /twilio -> twilio_handler
      - /client -> client_handler
    """
    print(f"Incoming connection on path: {path}")
    if path == "/twilio":
        await twilio_handler(websocket)
    elif path == "/client":
        await client_handler(websocket)
    else:
        print(f"Unknown path: {path}")
        await websocket.close()

def start_fraud_server(host="0.0.0.0", port=5000):
    """
    Starts the async websockets server in a fresh asyncio loop.
    This function is meant to run in a dedicated thread.
    """
    global FRAUD_ALERT_QUEUE
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    FRAUD_ALERT_QUEUE = asyncio.Queue()
    print(f"Starting fraud websocket server on ws://{host}:{port}")
    # For production with SSL, create ssl_context and pass ssl=ssl_context to serve()
    server_coroutine = websockets.serve(router, host, port)
    server = loop.run_until_complete(server_coroutine)
    try:
        loop.run_forever()
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()

# ---- Entrypoint ----
if __name__ == "__main__":
    # Run the fraud server in a daemon thread so it shuts down with the main process.
    # Use use_reloader=False to avoid starting twice during Flask debug reloader.
    ws_thread = threading.Thread(target=start_fraud_server, kwargs={"host": "0.0.0.0", "port": 5000}, daemon=True)
    ws_thread.start()
    # Start Flask. If you want reloader, ensure you handle double-start issues.
    app.run(host='0.0.0.0', port=3000, debug=True, use_reloader=False)
