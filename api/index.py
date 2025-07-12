# api/index.py

import asyncio
import base64
import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from hume import HumeAsyncClient
from hume.models.config import VoiceConfig

# Initialize FastAPI app
app = FastAPI()

# Load environment variables
HUME_API_KEY = os.getenv("HUME_API_KEY")
HUME_SECRET_KEY = os.getenv("HUME_SECRET_KEY")

# Create a single, reusable Hume client instance
hume_client = HumeAsyncClient(HUME_API_KEY)


# --- FastAPI Endpoints ---

@app.get("/")
async def root():
    """
    Serve the frontend HTML file.
    """
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Handle the WebSocket connection for real-time voice chat.
    """
    await websocket.accept()

    config = VoiceConfig.from_id(os.getenv("HUME_CONFIG_ID"))

    try:
        async with hume_client.empathic_voice.chat(config, secret_key=HUME_SECRET_KEY) as socket:
            print("Hume socket connected.")

            # Coroutine to handle receiving messages from Hume and sending to the client
            async def from_hume():
                async for message in socket:
                    # A more robust way to serialize the message
                    message_dict = message.model_dump()
                    await websocket.send_json(message_dict)

            # Coroutine to handle receiving messages from the client and sending to Hume
            async def from_client():
                async for message in websocket.iter_bytes():
                    # The client sends raw audio bytes. We forward them to Hume.
                    await socket.send_bytes(message)

            # Run both coroutines concurrently
            await asyncio.gather(from_hume(), from_client())

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("WebSocket connection closed.")
