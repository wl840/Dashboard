from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import GroundedChatService

router = APIRouter(tags=["ai"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, session: DatabaseSession):
    try:
        return GroundedChatService(session).answer(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
