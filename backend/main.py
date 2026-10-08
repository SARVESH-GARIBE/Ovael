from fastapi import FastAPI

from api.detections import router as detections_router

app = FastAPI(title="Ovael.ai Backend")
app.include_router(detections_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
