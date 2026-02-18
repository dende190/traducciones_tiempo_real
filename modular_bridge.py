import asyncio
import os
import sys
import pyaudio
import numpy as np
import json
import websockets
import time
import re
import uuid
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

# Voice IDs
# Incoming (EN->ES): Generic Spanish Voice (Sonic Multilingual supports it)
# Outgoing (ES->EN): Cloned Voice ID (User provided)
VOICE_ID_OUTGOING = os.getenv("VOICE_ID_OUTGOING", "a0e99841-438c-4a64-b679-ae501e7d6091") # Default to generic if missing
VOICE_ID_INCOMING = "a0e99841-438c-4a64-b679-ae501e7d6091" # Generic Sonic ID

class TranslationPipeline:
    def __init__(self, name, input_device_name, output_device_name, stt_lang, llm_prompt, tts_voice_id):
        self.name = name
        self.input_device_name = input_device_name
        self.output_device_name = output_device_name
        self.stt_lang = stt_lang
        self.llm_prompt = llm_prompt
        self.tts_voice_id = tts_voice_id
        
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        
        self.groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        self.cartesia_client = AsyncCartesia(api_key=CARTESIA_API_KEY)
        
        self.is_running = False
        self.input_device_index = self.get_device_index(self.input_device_name, is_input=True)
        self.output_device_index = self.get_device_index(self.output_device_name, is_input=False)
        
        # Queues
        self.transcript_queue = asyncio.Queue()
        self.audio_queue = asyncio.Queue()
        
        self.log(f"Initialized Pipeline '{self.name}'")
        self.log(f"  Input: {self.input_device_name} (Index: {self.input_device_index})")
        self.log(f"  Output: {self.output_device_name} (Index: {self.output_device_index})")

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}][{self.name}] {message}")

    def get_device_index(self, name_fragment, is_input=True):
        if not name_fragment: 
            return None
            
        count = self.p.get_device_count()
        # Try exact match first, then substring
        for i in range(count):
            info = self.p.get_device_info_by_index(i)
            if is_input and info["maxInputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    return i
            elif not is_input and info["maxOutputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    return i
        
        if not is_input:
            # Fallback for output: Default device
            try:
                default_idx = self.p.get_default_output_device_info()["index"]
                self.log(f"Warning: Output device '{name_fragment}' not found. Using default index {default_idx}.")
                return default_idx
            except:
                return None
        return None

    async def start(self):
        if self.input_device_index is None:
            self.log(f"Error: Input device '{self.input_device_name}' not found.")
            return

        self.is_running = True

        # Initialize Output Stream
        if self.output_device_index is not None:
            self.output_stream = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=44100,
                output=True,
                output_device_index=self.output_device_index
            )

        # Deepgram Configuration
        host = "wss://api.deepgram.com"
        path = "/v1/listen"
        # Deepgram Nova-2 params
        params = (
            f"model=nova-2"
            f"&language={self.stt_lang}"
            "&smart_format=true"
            "&encoding=linear16"
            "&sample_rate=16000"
            "&interim_results=true"
            "&endpointing=300"
        )
        url = f"{host}{path}?{params}"
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        self.log(f"Connecting to Deepgram ({self.stt_lang})...")

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                self.log("Deepgram Connected!")

                # Open Input Stream
                self.input_stream = self.p.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=self.input_device_index,
                    frames_per_buffer=CHUNK
                )
                self.log("Listening...")

                # Start tasks
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
                    self.log("Stopping loop...")
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
            self.log(f"Pipeline Error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        if self.input_stream:
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except: pass
        if self.output_stream:
            try:
                self.output_stream.stop_stream()
                self.output_stream.close()
            except: pass
        self.p.terminate()

    async def receive_loop(self, ws):
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
                                self.log(f"STT: {transcript}")
                                await self.transcript_queue.put(transcript)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            self.log(f"Receive Error: {e}")

    async def processing_loop(self):
        while self.is_running:
            try:
                self.log("Connecting to Cartesia TTS...")
                async with self.cartesia_client.tts.websocket_connect() as ws:
                    self.log("Cartesia TTS Connected")
                    
                    # Receiver Task (Full Duplex)
                    receiver_task = asyncio.create_task(self.cartesia_receive_loop(ws))
                    
                    try:
                        while self.is_running:
                            text = await self.transcript_queue.get()
                            self.log(f"Translating: '{text}'")
                            
                            try:
                                # Groq Translation (Streaming)
                                stream = await self.groq_client.chat.completions.create(
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": self.llm_prompt
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
                                turn_id = str(uuid.uuid4())
                                
                                async for chunk in stream:
                                    content = chunk.choices[0].delta.content
                                    if content:
                                        buffer += content
                                        if re.search(r'[.?!,;:]', buffer):
                                            await self.send_cartesia_payload(ws, buffer, turn_id, continue_stream=True)
                                            buffer = ""
                                
                                if buffer.strip():
                                    await self.send_cartesia_payload(ws, buffer, turn_id, continue_stream=False)
                                else:
                                    # If buffer empty but stream ended, we might want to signal end?
                                    # But we can't send empty transcript. 
                                    pass

                            except Exception as e:
                                self.log(f"Processing Error: {e}")
                                if "websocket" in str(type(e)).lower(): raise e
                            finally:
                                self.transcript_queue.task_done()
                    finally:
                        receiver_task.cancel()
                        try: await receiver_task
                        except: pass
            except Exception as e:
                self.log(f"Cartesia Reconnect: {e}")
                await asyncio.sleep(2)

    async def send_cartesia_payload(self, ws, text, context_id, continue_stream=True):
        self.log(f"TTS >> {text} (continue={continue_stream})")
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
                "id": self.tts_voice_id
            },
            "output_format": output_format,
            "context_id": context_id,
            "continue": continue_stream
        }
        await ws.send(payload)

    async def cartesia_receive_loop(self, ws):
        try:
            async for chunk in ws:
                audio = getattr(chunk, "audio", None)
                if audio:
                    # self.log(f"Received Audio Chunk: {len(audio)} bytes")
                    await self.audio_queue.put(audio)
        except Exception as e:
            self.log(f"Cartesia Receiver Error: {e}")

    async def playback_loop(self):
        while True:
            audio_data = await self.audio_queue.get()
            try:
                if self.output_stream:
                     # self.log(f"Playing Chunk: {len(audio_data)} bytes")
                     await asyncio.to_thread(self.output_stream.write, audio_data)
            except Exception as e:
                self.log(f"Playback Error: {e}")
            finally:
                self.audio_queue.task_done()

class BiDirectionalBridge:
    def __init__(self):
        # Pipeline 1: Incoming (Remote EN -> Local ES)
        # Input: BlackHole 2ch (System Audio)
        # Output: Headphones/Default
        self.incoming = TranslationPipeline(
            name="INCOMING (EN->ES)",
            input_device_name="BlackHole 2ch",
            output_device_name="Headphones", # Fallbacks to default
            stt_lang="en-US",
            llm_prompt="Translate English to Spanish. Output ONLY Spanish.",
            tts_voice_id=VOICE_ID_INCOMING
        )

        # Pipeline 2: Outgoing (Local ES -> Remote EN)
        # Input: Microphone
        # Output: BlackHole 16ch (Virtual Mic for Meet)
        self.outgoing = TranslationPipeline(
            name="OUTGOING (ES->EN)",
            input_device_name="Microphone", # Matches built-in mic usually
            output_device_name="BlackHole 16ch",
            stt_lang="es",
            llm_prompt="Translate Spanish to English. Output ONLY English.",
            tts_voice_id=VOICE_ID_OUTGOING
        )

    async def start(self):
        print("Starting Bi-Directional Translation Bridge...")
        
        # Run both pipelines concurrently
        await asyncio.gather(
            self.incoming.start(),
            self.outgoing.start()
        )

if __name__ == "__main__":
    if not all([DEEPGRAM_API_KEY, GROQ_API_KEY, CARTESIA_API_KEY]):
        print("ERROR: Missing API Keys. Please check .env")
        sys.exit(1)

    try:
        bridge = BiDirectionalBridge()
        asyncio.run(bridge.start())
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Fatal Error: {e}")

