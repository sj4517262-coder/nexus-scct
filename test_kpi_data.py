import asyncio
import websockets

async def test():
    print("Connecting to KPI WebSocket...")

    async with websockets.connect("ws://localhost:8000/ws/kpis") as ws:
        print("WEBSOCKET CONNECTED")

        message = await asyncio.wait_for(ws.recv(), timeout=5)

        print("KPI MESSAGE RECEIVED:")
        print(message)

asyncio.run(test())
