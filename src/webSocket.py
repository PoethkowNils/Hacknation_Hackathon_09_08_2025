import asyncio
import websockets

async def handler(websocket):
    print("PYTHON: WebSocket-Verbindung wurde akzeptiert! ✅")
    try:
        async for message in websocket:
            chunk = message
            print(f"PYTHON: Empfange Audio-Daten-Chunk der Länge: {len(chunk)} Bytes. Datentyp: {type(chunk)}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"PYTHON: Verbindung geschlossen. Code: {e.code}, Grund: {e.reason}")
    finally:
        print("PYTHON: Handler beendet.")

async def main():
    print("PYTHON: Starte den WebSocket-Server...")
    async with websockets.serve(handler, "localhost", 5005):
        print("PYTHON: Server lauscht auf: ws://localhost:5005")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())