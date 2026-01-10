"""
Local MLX Embeddings Server

FastAPI server providing embeddings via sentence-transformers.
Uses BAAI/bge-m3 model (1024 dimensions) to match Voyage voyage-3-lite.

Endpoints:
- GET  /health       - Health check with model info
- POST /v1/embeddings - Generate embeddings for texts
"""

import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# Configuration
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8100"))

# Global model instance
model: Optional[SentenceTransformer] = None


class EmbedRequest(BaseModel):
    """Request body for embedding generation"""
    texts: List[str]
    model: str = "bge-m3"  # Ignored, using configured model


class EmbedResponse(BaseModel):
    """Response with embeddings and metadata"""
    embeddings: List[List[float]]
    model: str
    dimensions: int
    usage: dict


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model: str
    dimensions: int
    ready: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup"""
    global model
    print(f"[Embeddings Server] Loading model: {MODEL_NAME}")
    start = time.time()
    model = SentenceTransformer(MODEL_NAME)
    elapsed = time.time() - start
    dims = model.get_sentence_embedding_dimension()
    print(f"[Embeddings Server] Model loaded in {elapsed:.1f}s. Dimensions: {dims}")
    yield
    print("[Embeddings Server] Shutting down...")


app = FastAPI(
    title="MLX Embeddings Server",
    description="Local embeddings server using sentence-transformers",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - same as health"""
    return await health()


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    if not model:
        return HealthResponse(
            status="loading",
            model=MODEL_NAME,
            dimensions=0,
            ready=False,
        )

    return HealthResponse(
        status="healthy",
        model=MODEL_NAME,
        dimensions=model.get_sentence_embedding_dimension(),
        ready=True,
    )


@app.post("/v1/embeddings", response_model=EmbedResponse)
async def create_embeddings(request: EmbedRequest):
    """
    Generate embeddings for a list of texts.

    Compatible with OpenAI-style embedding API format.
    """
    if not model:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded yet. Please wait for startup to complete.",
        )

    if not request.texts:
        raise HTTPException(
            status_code=400,
            detail="texts array is required and cannot be empty",
        )

    if len(request.texts) > 256:
        raise HTTPException(
            status_code=400,
            detail="Maximum 256 texts per request",
        )

    start = time.time()

    # Generate embeddings with normalization (important for cosine similarity)
    embeddings = model.encode(
        request.texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    elapsed = time.time() - start

    return EmbedResponse(
        embeddings=embeddings.tolist(),
        model=MODEL_NAME,
        dimensions=embeddings.shape[1],
        usage={
            "texts_processed": len(request.texts),
            "processing_time_ms": int(elapsed * 1000),
            "texts_per_second": round(len(request.texts) / elapsed, 1) if elapsed > 0 else 0,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
