from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="2Care Voice AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "2care-voice-agent"}

from app.agent.orchestrator import handle_websocket_connection
from pydantic import BaseModel
import asyncio

@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    await handle_websocket_connection(websocket)

class CampaignRequest(BaseModel):
    patient_id: str
    campaign_type: str

@app.post("/campaign/outbound")
async def trigger_outbound_campaign(req: CampaignRequest):
    # Simulates adding an outbound call job to a queue
    asyncio.create_task(simulate_outbound_call(req.patient_id, req.campaign_type))
    return {"status": "Job queued"}

async def simulate_outbound_call(patient_id: str, type: str):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Simulating Twilio outbound call to {patient_id} for {type}")
    await asyncio.sleep(2)
    logger.info("Call connected, agent taking over...")
