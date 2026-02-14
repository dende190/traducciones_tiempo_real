import asyncio
import os
import sys
import time
import pyaudio
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import (
    LiveConnectConfig,
    PrebuiltVoiceConfig,
    SpeechConfig,
    VoiceConfig,
)

# Load environment variables
load_dotenv()

# Configuration Constants
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
TARGET_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025" 

class VAD:
    """
    Simple Voice Activity Detector based on RMS energy with hysteresis.
    """
    def __init__(self, start_threshold=500, stop_threshold=300, min_speech_duration_ms=100, min_silence_duration_ms=400):
        self.start_threshold = start_threshold
        self.stop_threshold = stop_threshold
        self.min_speech_ms = min_speech_duration_ms
        self.min_silence_ms = min_silence_duration_ms
        
        self.speech_active = False
        self.consecutive_speech_ms = 0
        self.consecutive_silence_ms = 0
        self.last_state = "silence"

    def is_speech(self, audio_data, chunk_ms):
         # Calculate RMS
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        # Safe cast to avoid overflow
        if len(audio_np) == 0: return False
        rms = np.sqrt(np.mean(audio_np.astype(np.float64)**2))
        
        # State Machine
        if not self.speech_active:
            if rms > self.start_threshold:
                self.consecutive_speech_ms += chunk_ms
                if self.consecutive_speech_ms >= self.min_speech_ms:
                    self.speech_active = True
                    self.consecutive_silence_ms = 0
                    # print(f"[Speech START] RMS: {rms}")
            else:
                self.consecutive_speech_ms = 0
        else:
            if rms < self.stop_threshold:
                self.consecutive_silence_ms += chunk_ms
                if self.consecutive_silence_ms >= self.min_silence_ms:
                    self.speech_active = False
                    self.consecutive_speech_ms = 0
                    print(f"[Speech END] RMS: {rms}")
            else:
                self.consecutive_silence_ms = 0
                
        return self.speech_active

class AudioBridge:
    def __init__(self, api_key):
        self.api_key = api_key
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.client = None
        self.stop_event = asyncio.Event()
        self.vad = VAD()

    def get_device_index(self, name_fragment, is_input=True):
        count = self.p.get_device_count()
        print(f"\nScanning {count} audio devices...")
        found_index = None
        for i in range(count):
            info = self.p.get_device_info_by_index(i)
            print(f"Device {i}: {info['name']} (In: {info['maxInputChannels']}, Out: {info['maxOutputChannels']})")
            if is_input and info["maxInputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    found_index = i
            elif not is_input and info["maxOutputChannels"] > 0:
                if name_fragment.lower() in info["name"].lower():
                    found_index = i
        return found_index

    async def connect_gemini(self):
        self.client = genai.Client(api_key=self.api_key, http_options={"api_version": "v1alpha"})
        
        input_device_index = self.get_device_index("BlackHole 2ch", is_input=True)
        if input_device_index is None:
            raise ValueError("BlackHole 2ch input device not found. Please install BlackHole.")
        
        # Output Device Selection Logic
        output_device_index = None
        
        # 1. Check env var override
        env_index = os.environ.get("OUTPUT_DEVICE_INDEX")
        if env_index:
            try:
                output_device_index = int(env_index)
                print(f"Using forced Output Device Index from .env: {output_device_index}")
            except ValueError:
                print("Invalid OUTPUT_DEVICE_INDEX in .env")

        # 2. Try specific physical devices to avoid Multi-Output loops
        if output_device_index is None:
            output_device_index = self.get_device_index("External Headphones", is_input=False) or \
                                  self.get_device_index("Headphones", is_input=False) or \
                                  self.get_device_index("MacBook Pro Speakers", is_input=False) or \
                                  self.get_device_index("Speakers", is_input=False)

        # 3. Fallback to default
        if output_device_index is None:
            try:
                default_output = self.p.get_default_output_device_info()
                output_device_index = default_output["index"]
                print("Using System Default Output Device.")
            except IOError:
                print("No default output device found.")

        if output_device_index is None:
             raise RuntimeError("Could not find a valid output device! Check your audio settings.")

        print(f"Using Input Device: {input_device_index} (BlackHole)")
        print(f"Using Output Device: {output_device_index}")

        # Open streams
        self.input_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=input_device_index,
            frames_per_buffer=CHUNK,
        )

        self.output_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            output_device_index=output_device_index,
        )
        
        # Modified config
        config = LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name="Puck"
                    )
                )
            ),
        )

        async with self.client.aio.live.connect(model=TARGET_MODEL, config=config) as session:
            print("Connected to Gemini!")
            
            # Send initial system instruction as a text message
            print("Sending system instruction...")
            await session.send(input="You are a simultaneous translator. Translate English audio to Spanish text/audio immediately. Keep it short.", end_of_turn=True)
            
            # Start tasks
            send_task = asyncio.create_task(self.send_audio_loop(session))
            receive_task = asyncio.create_task(self.receive_audio_loop(session))
            
            await asyncio.gather(send_task, receive_task)

    async def send_audio_loop(self, session):
        try:
            print("Starting audio send loop...")
            loop = asyncio.get_running_loop()
            ms_per_chunk = int((CHUNK / RATE) * 1000)
            
            while not self.stop_event.is_set():
                try:
                    # Run blocking read in executor
                    data = await loop.run_in_executor(
                        None, 
                        lambda: self.input_stream.read(CHUNK, exception_on_overflow=False)
                    )
                    
                    # Local VAD Processing
                    if self.vad.is_speech(data, ms_per_chunk):
                         # Send actual audio
                         await session.send_realtime_input(media={"data": data, "mime_type": "audio/pcm"})
                         print(".", end="", flush=True) 
                    else:
                         # Send silence (zeros) to "gate" the noise
                         # Crucial for Gemini to realize the turn has ended
                         silence = b'\x00' * len(data)
                         await session.send_realtime_input(media={"data": silence, "mime_type": "audio/pcm"})
                         # print("s", end="", flush=True) # Optional: indicate silence
                    
                    # No sleep needed here as run_in_executor yields
                except IOError as e:
                    print(f"Input Stream Error: {e}")
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error in send loop: {e}")
            self.stop_event.set()

    async def receive_audio_loop(self, session):
        # ... (same as before, just ensuring we print debugs)
        print("Starting receive loop...")
        try:
            async for response in session.receive():
                if self.stop_event.is_set():
                    break
                
                server_content = response.server_content
                if server_content:
                    if server_content.turn_complete:
                        print("\n[Turn Complete]")
                    
                    model_turn = server_content.model_turn
                    if model_turn:
                        if model_turn.parts:
                            for part in model_turn.parts:
                                if part.text:
                                    print(f"Gemini (Text): {part.text}")
                                if part.inline_data:
                                    # print(f"[Audio Chunk Received: {len(part.inline_data.data)} bytes]")
                                    self.output_stream.write(part.inline_data.data)
                        else:
                            print("[Model Turn with no parts]")
                
                if response.tool_call:
                     print(f"Tool Call: {response.tool_call}")

        except Exception as e:
             print(f"Error in receive loop: {e}")
             self.stop_event.set()

    def run(self):
        try:
            asyncio.run(self.connect_gemini())
        except KeyboardInterrupt:
            print("\nStopping...")
        except Exception as e:
            print(f"Fatal Error: {e}")
        finally:
            self.stop_event.set()
            if self.input_stream and self.input_stream.is_active():
                self.input_stream.stop_stream()
                self.input_stream.close()
            if self.output_stream and self.output_stream.is_active():
                self.output_stream.stop_stream()
                self.output_stream.close()
            self.p.terminate()

if __name__ == "__main__":
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Please set GOOGLE_API_KEY environment variable in .env file.")
        sys.exit(1)
    
    bridge = AudioBridge(api_key)
    bridge.run()
