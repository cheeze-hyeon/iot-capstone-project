import asyncio
import json
import websockets


async def main():
    async with websockets.connect("ws://localhost:8765") as ws:
        async for msg in ws:
            data = json.loads(msg)
            print(data)


asyncio.run(main())
