import asyncio
import websockets
import base64

async def handler(websocket):
    print("SERVER: WebSocket-Verbindung wurde akzeptiert! ✅")
    try:
        async for message in websocket:
            chunk = message
            print(f"SERVER: Empfange Audio-Daten-Chunk der Länge: {len(chunk)} Bytes. Datentyp: {type(chunk)}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"SERVER: Verbindung geschlossen. Code: {e.code}, Grund: {e.reason}")
    finally:
        print("SERVER: Handler beendet.")

async def main():
    print("SERVER: Starte den WebSocket-Server...")
    async with websockets.serve(handler, "localhost", 5005):
        print("SERVER: Server lauscht auf: ws://localhost:5005")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())