import asyncio
import os
import sys
import pyaudio
import numpy as np
import json
import websockets
import time
from dotenv import load_dotenv

from groq import AsyncGroq
from cartesia import AsyncCartesia

# Load environment variables
load_dotenv()

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 2048

# API Config Check
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

class ModularBridge:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        
        # Initialize Clients
        self.groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        self.cartesia_client = AsyncCartesia(api_key=CARTESIA_API_KEY)
        # Deepgram client not needed for manual websocket
        
        # State
        self.is_running = True
        self.input_device_index = self.get_device_index("BlackHole 2ch", is_input=True)
        self.output_device_index = self.get_output_device_index()
        
        # Queues for non-blocking processing
        self.transcript_queue = asyncio.Queue()
        self.audio_queue = asyncio.Queue()

        print(f"Input Device: {self.input_device_index}")
        print(f"Output Device: {self.output_device_index}")

    def get_device_index(self, name_fragment, is_input=True):
        count = self.p.get_device_count()
        for i in range(count):
            info = self.p.get_device_info_by_index(i)
            if is_input and info["maxInputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    return i
            elif not is_input and info["maxOutputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    return i
        return None

    def get_output_device_index(self):
        env_index = os.environ.get("OUTPUT_DEVICE_INDEX")
        if env_index:
            try:
                return int(env_index)
            except ValueError:
                pass
        
        idx = self.get_device_index("External Headphones", is_input=False) or \
              self.get_device_index("Headphones", is_input=False) or \
              self.get_device_index("MacBook Pro Speakers", is_input=False) or \
              self.get_device_index("Speakers", is_input=False)
        
        if idx is not None:
            return idx

        try:
            return self.p.get_default_output_device_info()["index"]
        except:
             return None

    async def start(self):
        if self.input_device_index is None:
            print("Error: BlackHole 2ch not found. Please install BlackHole.")
            return

        print("Initializing Audio Output...")
        self.output_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=44100,
            output=True,
            output_device_index=self.output_device_index
        )
        
        # Deepgram WebSocket URL
        host = "wss://api.deepgram.com"
        path = "/v1/listen"
        params = (
            "model=nova-2"
            "&language=en-US"
            "&smart_format=true"
            "&encoding=linear16"
            "&sample_rate=16000"
            "&interim_results=true"
            "&endpointing=300" 
        )
        url = f"{host}{path}?{params}"
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}"
        }

        print(f"Connecting to Deepgram: {url}")
        
        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                print("Deepgram Connected!")

                self.input_stream = self.p.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=self.input_device_index,
                    frames_per_buffer=CHUNK
                )
                print("Listening... (Speak into BlackHole 2ch)")
                
                # Start background tasks
                receive_task = asyncio.create_task(self.receive_loop(ws))
                process_task = asyncio.create_task(self.processing_loop())
                playback_task = asyncio.create_task(self.playback_loop())
                
                try:
                    while self.is_running:
                        data = await asyncio.to_thread(self.input_stream.read, CHUNK, exception_on_overflow=False)
                        if len(data) > 0:
                            await ws.send(data)
                        else:
                             await asyncio.sleep(0.01)

                finally:
                    print("Stopping main loop...")
                    receive_task.cancel()
                    process_task.cancel()
                    playback_task.cancel()
                    try:
                        await receive_task
                        await process_task
                        await playback_task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            print(f"Connection Error: {e}")
        finally:
            self.stop()

    async def receive_loop(self, ws):
        """
        Receives JSON responses from Deepgram and pushes valid transcripts to queue.
        """
        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    
                    if "channel" in data:
                        alternatives = data["channel"].get("alternatives", [])
                        if alternatives:
                            transcript = alternatives[0].get("transcript", "")
                            is_final = data.get("is_final", False)
                            
                            if transcript and is_final:
                                print(f"\n[User]: {transcript}")
                                await self.transcript_queue.put(transcript)
                    
                    if "type" in data and data["type"] == "Metadata":
                         print(f"Deepgram Metadata: {data}")

                except json.JSONDecodeError:
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("Deepgram connection closed")
        except Exception as e:
            print(f"Receive Loop Error: {e}")

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    async def processing_loop(self):
        """
        Consumes transcripts, translates them, and pushes audio to playback queue.
        Maintains a persistent connection to Cartesia for lower latency.
        Uses Streaming Translation to improve TTFB.
        """
        import re
        
        while self.is_running:
            try:
                self.log("Connecting to Cartesia TTS...")
                async with self.cartesia_client.tts.websocket_connect() as ws:
                    self.log("Cartesia TTS Connected")
                    
                    while self.is_running:
                        text = await self.transcript_queue.get()
                        self.log(f"Processing: '{text}'")
                        
                        try:
                            # 1. Groq Translation (Streaming)
                            stream = await self.groq_client.chat.completions.create(
                                messages=[
                                    {
                                        "role": "system",
                                        "content": "Translate the user input from English to Spanish immediately. Output ONLY the Spanish translation."
                                    },
                                    {
                                        "role": "user",
                                        "content": text,
                                    }
                                ],
                                model="llama-3.1-8b-instant",
                                temperature=0.3,
                                max_tokens=1024,
                                stream=True,
                            )
                            
                            buffer = ""
                            import uuid
                            # Use a unique context for this entire sentence/turn
                            # This helps Cartesia understand these chunks belong together (if supported)
                            turn_context_id = str(uuid.uuid4())
                            
                            async for chunk in stream:
                                content = chunk.choices[0].delta.content
                                if content:
                                    buffer += content
                                    # Check for punctuation to flush chunks
                                    # Flush on: . ? ! , : ;
                                    if re.search(r'[.?!,;:]', buffer):
                                        await self.send_to_cartesia(ws, buffer, turn_context_id)
                                        buffer = ""
                            
                            # Flush remaining buffer
                            if buffer.strip():
                                await self.send_to_cartesia(ws, buffer, turn_context_id)

                            self.log("Translation & TTS Request Sent for Turn")

                        except Exception as e:
                            self.log(f"Processing Task Error: {e}")
                            if "websocket" in str(type(e)).lower() or "connection" in str(e).lower():
                                raise e
                        finally:
                            self.transcript_queue.task_done()

            except Exception as e:
                self.log(f"Cartesia Connection Error (Reconnecting in 2s): {e}")
                await asyncio.sleep(2)

    async def send_to_cartesia(self, ws, text, context_id):
        """Helper to send text chunk to Cartesia"""
        self.log(f"[Groq Stream]: {text}")
        
        output_format = {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 44100,
        }
        
        payload = {
            "model_id": "sonic-multilingual",
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": "a0e99841-438c-4a64-b679-ae501e7d6091" 
            },
            "output_format": output_format,
            "context_id": context_id,
            "continue": True # Hint that this is part of a stream
        }
        
        await ws.send(payload)

        # Receive chunks immediately for this segment
        # Note: If we are pipelining, we might have multiple requests in flight.
        # But Cartesia websocket is bidirectional. 
        # Ideally, we should have a separate 'reader' task for the websocket if we want true full-duplex 
        # (sending next chunk while receiving audio for previous).
        # However, for now, let's await the response for this chunk to keep order simple.
        # Wait, if we wait for 'done', we block the next Groq chunk.
        # But 'done' comes fast for short chunks.
        
        async for chunk in ws:
            audio = getattr(chunk, "audio", None)
            if audio:
                await self.audio_queue.put(audio)
            
            if getattr(chunk, "done", False):
                break

    async def playback_loop(self):
        """
        Consumes audio chunks and plays them.
        """
        while True:
            audio_data = await self.audio_queue.get()
            try:
                if self.output_stream:
                     # Run blocking write in thread
                     await asyncio.to_thread(self.output_stream.write, audio_data)
            except Exception as e:
                print(f"Playback Error: {e}")
            finally:
                self.audio_queue.task_done()

    def stop(self):
        self.is_running = False
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        self.p.terminate()

if __name__ == "__main__":
    if not all([DEEPGRAM_API_KEY, GROQ_API_KEY, CARTESIA_API_KEY]):
        print("ERROR: Missing API Keys. Please check .env")
        sys.exit(1)

    try:
        bridge = ModularBridge()
        asyncio.run(bridge.start())
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Fatal Error: {e}")

