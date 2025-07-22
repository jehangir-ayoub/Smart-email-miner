from fastapi import FastAPI
from email_webhook import router as email_router
from subscription import start_scheduler
import uvicorn

app = FastAPI(
    title="Microsoft Graph Email Webhook",
    description="FastAPI app that listens to Outlook email events and processes them with chunking, embedding, and vector storage.",
    version="1.0.0"
)

# Register the email webhook route
app.include_router(email_router)

# Trigger startup logic
@app.on_event("startup")
async def startup_event():
    print("\n[APP STARTUP] Initializing webhook subscription and scheduler...\n")
    start_scheduler()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
