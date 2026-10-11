from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.workflow.graph import init_graph, run_travel_agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: connect to MySQL and compile the graph once
    app.state.travel_graph, pool = await init_graph()
    yield
    # shutdown: close the MySQL pool
    pool.close()
    await pool.wait_closed()


app = FastAPI(title="AI Travel Planner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # React (Vite) dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    flight_results: str = ""
    hotel_results: str = ""
    itinerary: str = ""
    llm_calls: int = 0


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")
    try:
        return await run_travel_agent(request.app.state.travel_graph, req.message, req.thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))