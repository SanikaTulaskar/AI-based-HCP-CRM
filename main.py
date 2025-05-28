from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from ai_agent import process_chat_message, ChatRequest # Assuming ChatRequest is also in ai_agent.py or defined in main.py
from typing import List, Optional, Dict, Any
from datetime import date
import logging
import os
from dotenv import load_dotenv

# SQLAlchemy specific imports
from sqlalchemy import create_engine, Column, Integer, String, Date, Enum as SQLAEnum
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
import enum # For Python enum to be used with SQLAlchemy Enum

# LangGraph and Groq related imports will go into the agent file.
from ai_agent import process_chat_message, ChatRequest # Ensure this import works

load_dotenv() # Load environment variables from .env

# --- Database Setup (SQLite with SQLAlchemy) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"  # This will create a file named sql_app.db in the backend directory

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} # check_same_thread is needed only for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic Models (Request/Response Schemas) ---
class InteractionSourceEnum(str, enum.Enum):
    STRUCTURED = "structured"
    CHAT_AI = "chat_ai"

class InteractionBase(BaseModel):
    hcpName: str = Field(..., example="Dr. Jane Doe")
    interactionDate: date = Field(..., example="2024-12-01")
    interactionType: str = Field(..., example="detail")
    productsDiscussed: Optional[str] = Field(None, example="ProductX, ProductY")
    keyDiscussionPoints: Optional[str] = Field(None, example="Discussed efficacy of ProductX for condition Z.")
    followUpActions: Optional[str] = Field(None, example="Send ProductX brochure by EOW.")
    source: InteractionSourceEnum = Field(default=InteractionSourceEnum.STRUCTURED, example="structured")

class InteractionCreate(InteractionBase):
    pass

class InteractionDB(InteractionBase):
    id: int

    class Config:
        orm_mode = True # Pydantic V1 way, or from_attributes = True for Pydantic V2

# --- SQLAlchemy Model (Database Table Schema) ---
class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    hcpName = Column(String, index=True)
    interactionDate = Column(Date)
    interactionType = Column(String)
    productsDiscussed = Column(String, nullable=True)
    keyDiscussionPoints = Column(String, nullable=True)
    followUpActions = Column(String, nullable=True)
    source = Column(SQLAEnum(InteractionSourceEnum), default=InteractionSourceEnum.STRUCTURED)


# Create database tables
# This function should ideally be called once at startup or managed by a migration tool like Alembic for production.
def create_db_and_tables():
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created (if they didn't exist).")

# --- FastAPI Application ---
app = FastAPI(
    title="AI-First CRM Backend",
    description="API for logging HCP interactions and conversational AI with SQLite.",
    version="0.1.1" # Updated version
)

# CORS (Cross-Origin Resource Sharing)
origins = [
    "http://localhost:5173", # Vite default
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints ---

# Call this on application startup to ensure tables are created
@app.on_event("startup")
async def on_startup():
    create_db_and_tables()
    # You can also initialize other things here, e.g., check Groq API key
    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "YOUR_GROQ_API_KEY_PLACEHOLDER":
        logger.warning("GROQ_API_KEY is not set or is a placeholder. AI features might not work.")


@app.post("/api/interactions", response_model=InteractionDB, status_code=201)
async def create_interaction_endpoint(
    interaction: InteractionCreate, db: Session = Depends(get_db)
):
    """
    Log a new HCP interaction (typically from the structured form or processed by AI).
    """
    logger.info(f"Received interaction log request: {interaction.model_dump_json()}")
    db_interaction = Interaction(**interaction.model_dump())
    db.add(db_interaction)
    db.commit()
    db.refresh(db_interaction)
    logger.info(f"Interaction logged with ID: {db_interaction.id}")
    return db_interaction

@app.get("/api/interactions", response_model=List[InteractionDB])
async def get_interactions_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve logged HCP interactions.
    """
    interactions = db.query(Interaction).offset(skip).limit(limit).all()
    logger.info(f"Retrieving {len(interactions)} interactions.")
    return interactions

# Chat interaction endpoint (integrates with LangGraph agent)
# Ensure ChatRequest Pydantic model is defined either here or imported from ai_agent.py
# (As defined in previous instructions, it's fine if it's in ai_agent.py and imported)

@app.post("/api/chat_interaction")
async def chat_handler(request: ChatRequest, db: Session = Depends(get_db)): # Added db session
    logger.info(f"Received chat request: {request.message}")
    try:
        agent_response = await process_chat_message(request) # process_chat_message is from ai_agent.py
        
        # If the agent extracted data, save it as an interaction
        if agent_response.get("extracted_data"):
            extracted_data = agent_response["extracted_data"]
            logger.info(f"AI extracted data, attempting to log interaction: {extracted_data}")
            
            # Map extracted_data to InteractionCreate Pydantic model
            # Ensure field names match or handle discrepancies
            interaction_data_to_save = {
                "hcpName": extracted_data.get("hcpName"),
                "interactionDate": extracted_data.get("interactionDate") or date.today().isoformat(),
                "interactionType": extracted_data.get("interactionType", "chat_derived"),
                "productsDiscussed": ", ".join(extracted_data.get("productsDiscussed", [])) if extracted_data.get("productsDiscussed") else None,
                "keyDiscussionPoints": extracted_data.get("keyDiscussionPoints"),
                "followUpActions": extracted_data.get("followUpActions"),
                "source": InteractionSourceEnum.CHAT_AI # Mark as sourced from AI
            }
            
            # Filter out None values for fields that are optional in Pydantic model but might be required by DB if not nullable
            interaction_data_to_save_cleaned = {k: v for k, v in interaction_data_to_save.items() if v is not None}

            if interaction_data_to_save_cleaned.get("hcpName"): # Require at least HCP name to save from chat
                try:
                    interaction_to_create = InteractionCreate(**interaction_data_to_save_cleaned)
                    db_interaction = Interaction(**interaction_to_create.model_dump())
                    db.add(db_interaction)
                    db.commit()
                    db.refresh(db_interaction)
                    logger.info(f"Interaction logged from chat AI with ID: {db_interaction.id}")
                    # Optionally, add confirmation of saving to the agent's reply
                    agent_response["reply"] += f" (Interaction details for {db_interaction.hcpName} logged with ID: {db_interaction.id})"
                    agent_response["saved_interaction_id"] = db_interaction.id # Send back the ID
                except Exception as e:
                    logger.error(f"Failed to save interaction from AI chat: {e}", exc_info=True)
                    agent_response["reply"] += " (There was an issue saving this interaction to the database.)"
            else:
                logger.info("Skipping database log from chat AI as hcpName was not extracted.")


        return agent_response # This now includes the AI's chat reply and potentially extracted data
    except Exception as e:
        logger.error(f"Error in chat_handler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


#if __name__ == "__main__":
    #import uvicorn
    # The on_startup event will call create_db_and_tables()
    #uvicorn.run(app, host="0.0.0.0", port=8000)