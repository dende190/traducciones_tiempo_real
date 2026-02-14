import asyncio
import os
import json
from dotenv import load_dotenv
from cartesia import AsyncCartesia

load_dotenv()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

async def test_tts():
    if not CARTESIA_API_KEY:
        print("Error: No API Key")
        return

    client = AsyncCartesia(api_key=CARTESIA_API_KEY)
    text = "Hola, esta es una prueba de voz."
    
    print(f"Testing TTS with text: '{text}'")

    try:
        async with client.tts.websocket_connect() as ws:
            print("Connected to Cartesia websocket.")
            
            output_format = {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 44100,
            }
            
            # Construct the payload
            import uuid
            context_id = str(uuid.uuid4())

            payload = {
                "model_id": "sonic-multilingual",
                "transcript": text,
                "voice": {
                    "mode": "id",
                    "id": "a0e99841-438c-4a64-b679-ae501e7d6091" 
                },
                "output_format": output_format,
                "context_id": context_id,
            }
            
            print("Sending payload...")
            await ws.send(payload)
            print("Payload sent. Waiting for chunks...")

            count = 0
            async for chunk in ws:
                count += 1
                print(f"Received chunk #{count}: Type={type(chunk)}")
                
                if isinstance(chunk, dict):
                    print(f"  Keys: {chunk.keys()}")
                    if "audio" in chunk:
                        print(f"  Audio len: {len(chunk['audio'])}")
                elif isinstance(chunk, (bytes, bytearray)):
                     print(f"  Bytes len: {len(chunk)}")
                else:
                     print(f"  Chunk content: {chunk}")
                
                if isinstance(chunk, dict) and chunk.get("done"):
                    print("Done signal received.")
                    break
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts())
