import asyncio
import inspect
from cartesia import AsyncCartesia

async def main():
    try:
        client = AsyncCartesia(api_key="fake")
        ws = await client.tts.websocket()
        print(f"ws.send signature: {inspect.signature(ws.send)}")
        print(f"ws.send is coroutine: {inspect.iscoroutinefunction(ws.send)}")
        await ws.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
