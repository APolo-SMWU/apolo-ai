"""APolo AI 서버의 FastAPI 진입점."""

from fastapi import FastAPI

app = FastAPI(title="APolo AI")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}