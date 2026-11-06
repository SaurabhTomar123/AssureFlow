from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.voice.voice_transcriber import transcribe_audio_note, route_voice_intent

router = APIRouter(prefix="/api/voice", tags=["Wispr Flow Voice Ingestion"])


class VoiceTextRequest(BaseModel):
    shop_id: str
    transcript: str


@router.post("/process-text")
def process_voice_transcript(req: VoiceTextRequest, db: Session = Depends(get_db)):
    try:
        res = route_voice_intent(req.transcript, req.shop_id, db)
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/upload-audio")
async def upload_audio_note(
    shop_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    audio_bytes = await file.read()
    transcript = transcribe_audio_note(audio_bytes, file.filename or "voice.ogg")
    res = route_voice_intent(transcript, shop_id, db)
    return res

