from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

app = FastAPI(title="OpenEtruscan Reranker")

class RerankRequest(BaseModel):
    query: str
    documents: list[str]

model = None

@app.on_event("startup")
def load_model():
    global model
    # CrossEncoder implicitly loads from HF Hub or local cache
    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

@app.post("/rerank")
def rerank(req: RerankRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model loading")
    pairs = [[req.query, doc] for doc in req.documents]
    scores = model.predict(pairs)
    # Return as list of floats
    return {"scores": scores.tolist()}
