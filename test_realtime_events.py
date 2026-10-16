import asyncio
import json
import websockets

async def test():
    print("Connecting to NEXUS event stream...")

    async with websockets.connect("ws://localhost:8000/ws/events") as ws:
        print("CONNECTED")
        print("Waiting for real Kafka/Redis events...")

        try:
            while True:
                message = await asyncio.wait_for(ws.recv(), timeout=30)
                print("EVENT RECEIVED:")
                print(json.dumps(json.loads(message), indent=2))
        except asyncio.TimeoutError:
            print("No event received in 30 seconds.")

asyncio.run(test())
