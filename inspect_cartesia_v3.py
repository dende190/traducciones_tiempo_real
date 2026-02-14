import asyncio
import inspect
import os
from dotenv import load_dotenv
from cartesia import AsyncCartesia

load_dotenv()

async def main():
    try:
        api_key = os.getenv("CARTESIA_API_KEY")
        if not api_key:
            print("No API key found")
            return
            
        client = AsyncCartesia(api_key=api_key)
            
        async with client.tts.websocket_connect() as ws:
            print(f"ws type: {type(ws)}")
            print(f"ws.send signature: {inspect.signature(ws.send)}")
            print(f"ws methods: {dir(ws)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
