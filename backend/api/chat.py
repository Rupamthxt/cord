import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from backend.intelligence.retrieval.search import search
from backend.core.services.db_manager import DBManager
from backend.extraction.ollama_client import ollama_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["Intelligence Chat"])
db_manager = DBManager()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    query: str = Field(..., description="User's follow-up question")
    workspace_id: str = Field(default="default_workspace", description="Strict workspace isolation scope")
    history: List[ChatMessage] = Field(default_factory=list, description="Previous chat logs in session")
    limit: int = Field(default=3, description="Maximum number of context chunks to pull")


@router.post("/chat")
async def handle_chat_diagnostics(body: ChatRequest):
    """
    Stateful operational assistant chat endpoint.
    Retrieves vector chunks and timelines relevant to the user's question 
    and answers using local Ollama llama3.2 client with full context citations.
    """
    logger.info(f"Received diagnostics chat query: '{body.query}' in workspace '{body.workspace_id}'")

    # 1. Retrieve semantic chunks & timeline events matching the current follow-up query
    try:
        search_res = search(query=body.query, limit=body.limit, workspace_id=body.workspace_id)
        chunks = search_res.get("results", [])
        events = db_manager.get_timeline(limit=5, workspace_id=body.workspace_id)
    except Exception as e:
        logger.error(f"Failed to fetch context for chat: {e}", exc_info=True)
        chunks = []
        events = []

    # 2. Format Context details for the LLM
    context_str = ""
    for i, c in enumerate(chunks):
        doc_title = c.get("metadata", {}).get("title") or c.get("source") or "document"
        context_str += f"\n[{i+1}] Source: {c.get('source')} | Title: {doc_title}\nContent: {c.get('content')}\n"

    events_str = ""
    for ev in events:
        events_str += f"- {ev.get('timestamp', 'N/A').split('T')[0]} | [{ev.get('event_type')}] {ev.get('title')}: {ev.get('summary')}\n"

    # 3. Assemble chat history context
    history_str = ""
    for msg in body.history[-5:]: # limit history loop to last 5 messages to avoid prompt bloat
        role_label = "Engineer" if msg.role == "user" else "CORD AI Assistant"
        history_str += f"{role_label}: {msg.content}\n"

    # 4. Formulate Prompt
    prompt = (
        f"You are the CORD AI Assistant, an expert SRE diagnostics helper.\n"
        f"Answer the Engineer's question using ONLY the retrieved system logs, vector chunks, and events context below.\n"
        f"Keep your response simplified, extremely clear, and direct. Avoid conversational filler, meta-remarks, or apologetic boilerplates about context limits.\n"
        f"Format the output using these sections:\n"
        f"**Root Cause**: (A 1-sentence explanation of what failed and why, in simple terms)\n"
        f"**Impact**: (What systems/services were affected)\n"
        f"**Remediation**: (How to correct the issue or what actions were taken to fix it)\n\n"
        f"Always cite source documents like [1], [2] next to your claims.\n\n"
        f"--- CONTEXT: SYSTEM LOG CHUNKS ---\n{context_str or 'No log chunks matched.'}\n\n"
        f"--- CONTEXT: EVENTS TIMELINE ---\n{events_str or 'No events logged.'}\n\n"
        f"--- CONVERSATION HISTORY ---\n{history_str}\n"
        f"Engineer: {body.query}\n"
        f"CORD AI Assistant:"
    )

    # 5. Generate completion
    # If Ollama server is offline, fall back to a programmatic rule-based response
    ollama_online = await ollama_client.is_available()
    if ollama_online:
        try:
            response_text = await ollama_client.generate(prompt=prompt, temperature=0.2)
        except Exception as e:
            logger.warning(f"Ollama generation failed: {e}. Falling back to programmatic reasoning.")
            response_text = None
    else:
        logger.info("Ollama server offline. Running local programmatic fallback.")
        response_text = None

    if not response_text:
        # Programmatic context-aware fallback
        if chunks:
            top_chunk = chunks[0]
            doc_title = top_chunk.get("metadata", {}).get("title") or top_chunk.get("source") or "document"
            snippet = top_chunk.get("content", "")
            
            # Let's extract sections from snippet if possible, else return clean sections
            import re
            clean_snippet = " ".join(snippet.strip().split())
            rc_match = re.search(r"Root\s+Cause:\s*(.*?)(?=(?:Observed\s+Effects:|Actions\s+Taken:|$))", clean_snippet, re.IGNORECASE)
            eff_match = re.search(r"(?:Observed\s+Effects|Impact):\s*(.*?)(?=(?:Actions\s+Taken|Root\s+Cause:|$))", clean_snippet, re.IGNORECASE)
            act_match = re.search(r"(?:Actions\s+Taken|Remediation):\s*(.*?)(?=(?:Root\s+Cause:|Observed\s+Effects:|$))", clean_snippet, re.IGNORECASE)
            
            rc = rc_match.group(1).strip() if rc_match else ""
            impact = eff_match.group(1).strip() if eff_match else ""
            remediation = act_match.group(1).strip() if act_match else ""
            
            if not rc:
                rc = f"Telemetry alert matches context: {clean_snippet[:150]}..."
            if not impact:
                impact = "Related systems mentioned in the retrieved context."
            if not remediation:
                remediation = "Follow standard runbook or check integration credentials."
                
            response_text = (
                f"**Root Cause**: [Ollama offline fallback] Refer to documentation *({doc_title})*: {rc}\n"
                f"**Impact**: {impact}\n"
                f"**Remediation**: {remediation}"
            )
        else:
            response_text = (
                f"**Root Cause**: [Ollama offline fallback] Insufficient workspace context / reasoning engine offline.\n"
                f"**Impact**: Unable to perform deep diagnostics search.\n"
                f"**Remediation**: Ensure connectors are configured and sync the workspace."
            )

    # 6. Format response payload containing supporting chunks for the frontend UI
    return {
        "query": body.query,
        "response": response_text,
        "evidence": {
            "chunks": chunks,
            "events": events
        }
    }
