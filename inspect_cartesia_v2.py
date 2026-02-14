import asyncio
import inspect
from cartesia import AsyncCartesia

async def main():
    try:
        client = AsyncCartesia(api_key="fake")
        # Inspect websocket_connect
        print(f"websocket_connect signature: {inspect.signature(client.tts.websocket_connect)}")
        
        # Check if it returns a context manager
        mgr = client.tts.websocket_connect()
        print(f"Return type: {type(mgr)}")
        print(f"Has __aenter__: {hasattr(mgr, '__aenter__')}")
        print(f"Has __await__: {hasattr(mgr, '__await__')}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
