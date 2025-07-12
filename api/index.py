# api/index.py

import asyncio
import base64
import os
import json
import wave
import io
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from hume import HumeAsyncClient
from hume.models.config import VoiceConfig

# --- Environment and Client Setup ---

# Check for required environment variables
HUME_API_KEY = os.getenv("HUME_API_KEY")
HUME_SECRET_KEY = os.getenv("HUME_SECRET_KEY")
HUME_CONFIG_ID = os.getenv("HUME_CONFIG_ID")

if not all([HUME_API_KEY, HUME_SECRET_KEY, HUME_CONFIG_ID]):
    # This will cause the Vercel deployment to fail if variables are not set, which is good for debugging.
    raise ValueError(
        "Please set HUME_API_KEY, HUME_SECRET_KEY, and HUME_CONFIG_ID "
        "as environment variables in your Vercel project."
    )

# Initialize FastAPI app and Hume client
app = FastAPI()
hume_client = HumeAsyncClient(HUME_API_KEY)


# --- Helper Function ---

def create_wav_file_from_pcm(
    pcm_data: bytes, sample_rate: int = 24000, sample_width: int = 2, channels: int = 1
) -> bytes:
    """Creates a WAV file in memory from raw PCM data."""
    with io.BytesIO() as wav_file:
        with wave.open(wav_file, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        return wav_file.getvalue()


# --- FastAPI Endpoints ---

@app.get("/")
async def root():
    """Serve the frontend HTML file."""
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle the WebSocket connection for real-time voice chat."""
    await websocket.accept()
    config = VoiceConfig.from_id(HUME_CONFIG_ID)

    try:
        async with hume_client.empathic_voice.chat(
            config, secret_key=HUME_SECRET_KEY
        ) as socket:
            print("Hume socket connected.")

            # Coroutine to handle receiving messages from Hume and sending to the client
            async def from_hume():
                async for message in socket:
                    if message.type == "audio_output" and message.data:
                        # Convert raw PCM audio from Hume into a playable WAV file
                        wav_data = create_wav_file_from_pcm(message.data)
                        # Send the WAV data as a base64 encoded string in a JSON object
                        await websocket.send_json({
                            "type": "audio_output",
                            "data": base64.b64encode(wav_data).decode("utf-8")
                        })
                    elif message.type != "audio_output":
                        # Send other message types (like user_message, assistant_message) as they are
                        await websocket.send_json(message.model_dump())

            # Coroutine to handle receiving messages from the client and sending to Hume
            async def from_client():
                async for message in websocket.iter_bytes():
                    # The client now sends raw PCM audio bytes. We forward them to Hume.
                    await socket.send_bytes(message)

            # Run both coroutines concurrently
            await asyncio.gather(from_hume(), from_client())

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("WebSocket connection closed.")
