import sys
from pathlib import Path

root = str(Path(__file__).resolve().parent.parent)
if root not in sys.path:
    sys.path.insert(0, root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import chat
from app.api.v1 import oss
from app.common.logger import setup_logging

setup_logging()

app = FastAPI(
    title="Personal Chief API",
    description="私厨",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/v1")
app.include_router(oss.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)