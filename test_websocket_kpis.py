import asyncio
import websockets

async def test():
    ws = await websockets.connect("ws://localhost:8000/ws/kpis")
    print("WEBSOCKET CONNECTED")

    await ws.send("ping")
    print("SENT: ping")

    await asyncio.sleep(2)

    await ws.close()
    print("WEBSOCKET CLOSED")

asyncio.run(test())
