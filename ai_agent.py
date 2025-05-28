import os
from typing import TypedDict, Annotated, Sequence, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_groq import ChatGroq
import json
import logging
from datetime import date

# --- Environment Variables & Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_PLACEHOLDER") # Replace with your actual key or set env var

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic Models for Structured Data Extraction ---
class ExtractedInteraction(BaseModel):
    hcpName: Optional[str] = Field(None, description="Name of the Healthcare Professional.")
    interactionDate: Optional[str] = Field(None, description="Date of interaction, ideally YYYY-MM-DD. If not specified, use today.")
    interactionType: Optional[str] = Field(None, description="Type of interaction (e.g., Detail, Follow-up, Meeting).")
    productsDiscussed: Optional[List[str]] = Field(None, description="List of products discussed.")
    keyDiscussionPoints: Optional[str] = Field(None, description="Key points from the discussion.")
    followUpActions: Optional[str] = Field(None, description="Any follow-up actions required.")
    sentiment: Optional[str] = Field(None, description="Overall sentiment of the HCP (e.g., positive, neutral, negative).")
    unclear_details: Optional[str] = Field(None, description="Any details that are unclear from the conversation and require clarification from the user.")


# --- LangGraph State ---
class InteractionState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    extracted_data: Optional[ExtractedInteraction]
    user_input: str # current user input
    context_summary: Optional[str] # Summary from Llama3 for context if needed


# --- LLM Initialization ---
# Gemma2 for primary conversational processing and extraction
gemma_llm = ChatGroq(
    temperature=0,
    model="gemma2-9b-it", # Using gemma2 for extraction and chat
    api_key=GROQ_API_KEY
)

# Llama3 for context summarization or deeper understanding if complex queries arise
llama_llm = ChatGroq(
    temperature=0.2,
    model="llama3-70b-8192", # Corrected Llama3 model name based on typical Groq offerings (check specific availability)
    # Note: Groq has models like 'llama3-70b-8192' or 'llama-3.1-70b-versatile'. I'll use 'llama3-70b-8192' as a common high-context one.
    # If 'llama-3.3-70b-versatile' is specifically available and preferred, use that.
    api_key=GROQ_API_KEY
)

# --- Tool for Gemma to use for extraction ---
gemma_structured_llm = gemma_llm.with_structured_output(ExtractedInteraction)

# --- Agent Nodes ---

async def get_context_summary(state: InteractionState):
    logger.info("---SUMMARIZING CONVERSATION FOR CONTEXT (LLAMA3)---")
    history = state["messages"]
    if len(history) < 3: # Not enough history to summarize meaningfully
        return {"context_summary": "No extensive prior context."}

    try:
        prompt = f"""
        Based on the following conversation history with a healthcare sales representative who is logging an interaction:
        {history}

        Summarize the key information already gathered about the current interaction being logged.
        This summary will be used as context for the primary AI assistant.
        Focus on entities like HCP name, date, products, and main topics.
        If crucial information is still missing, note that.
        """
        response = await llama_llm.ainvoke(prompt)
        summary = response.content
        logger.info(f"Context summary: {summary}")
        return {"context_summary": summary}
    except Exception as e:
        logger.error(f"Error during context summarization: {e}")
        return {"context_summary": "Error in generating context summary."}


async def extract_interaction_details(state: InteractionState):
    logger.info("---ATTEMPTING TO EXTRACT INTERACTION DETAILS (GEMMA2)---")
    user_input = state["user_input"]
    conversation_history = "\n".join([f"{msg.type}: {msg.content}" for msg in state["messages"]])
    context_summary = state.get("context_summary", "No prior summary.")

    # Get today's date for default interactionDate
    today_date_str = date.today().isoformat()

    prompt = f"""
    You are an AI assistant helping a healthcare sales representative log an interaction with a Healthcare Professional (HCP).
    Your goal is to extract structured information from the user's conversational input.
    If a field is not mentioned, do not invent data.
    If the interaction date is not specified, assume it is today: {today_date_str}.

    Current user input: "{user_input}"

    Consider the recent conversation history:
    {conversation_history}

    And the overall context summary (if available):
    {context_summary}

    Based *only* on the user's current input and the provided history/context, extract the following details.
    If some details are present in history but contradicted or updated by the current user input, prioritize the current input.
    If the user's input is a question or not providing loggable information, you can respond conversationally,
    but still try to extract if any partial information is present.
    If crucial details are missing or ambiguous, list them in 'unclear_details'.
    """
    try:
        # Using the LLM with structured output
        extracted_info: ExtractedInteraction = await gemma_structured_llm.ainvoke(prompt)
        logger.info(f"Extracted data: {extracted_info.model_dump_json(indent=2)}")
        return {"extracted_data": extracted_info}
    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        ai_response = AIMessage(content=f"I had trouble processing that. Could you please rephrase or provide more details? Error: {e}")
        return {"messages": [ai_response], "extracted_data": None}


async def conversational_agent_node(state: InteractionState):
    logger.info("---AI CONVERSATIONAL RESPONSE (GEMMA2)---")
    user_input = state["user_input"]
    extracted_data = state.get("extracted_data")
    messages_history = list(state["messages"]) # Make a mutable copy

    # Add user's latest message to history for context
    messages_history.append(HumanMessage(content=user_input))

    response_parts = []
    if extracted_data:
        if extracted_data.hcpName:
            response_parts.append(f"Okay, I've noted HCP: {extracted_data.hcpName}.")
        if extracted_data.interactionDate:
            response_parts.append(f"Date: {extracted_data.interactionDate}.")
        if extracted_data.productsDiscussed:
            response_parts.append(f"Products: {', '.join(extracted_data.productsDiscussed)}.")
        if extracted_data.keyDiscussionPoints:
            response_parts.append("Got the key points.")
        if extracted_data.followUpActions:
            response_parts.append("And the follow-up actions.")

        if extracted_data.unclear_details:
            response_parts.append(f"However, I need clarification on: {extracted_data.unclear_details}")
        elif not any(response_parts): # Nothing specific extracted, but no explicit unclear details
             response_parts.append("I've received your message.")
        else:
            response_parts.append("What else can I help you log about this interaction?")

    if not response_parts: # No data extracted, general conversation
        # Basic conversational prompt if no extraction occurred or extraction yielded nothing
        prompt = f"""You are a helpful AI assistant for a healthcare sales representative.
        The user is trying to log an interaction.
        User's current message: "{user_input}"
        Previous conversation:
        {state['messages']}

        Respond naturally and helpfully. If the user's input seems like a command or data for logging,
        acknowledge it. If it's a question, answer it.
        If you have extracted data (passed to you implicitly), you can confirm parts of it.
        Keep your responses concise and focused on completing the interaction log.
        """
        try:
            ai_response_content = (await gemma_llm.ainvoke(prompt)).content
        except Exception as e:
            logger.error(f"Error during conversational LLM call: {e}")
            ai_response_content = "I encountered an issue. Please try again."
    else:
        ai_response_content = " ".join(response_parts)


    ai_message = AIMessage(content=ai_response_content)
    logger.info(f"AI Response: {ai_response_content}")
    return {"messages": [ai_message]}


# --- Graph Definition ---
workflow = StateGraph(InteractionState)

# Add nodes
workflow.add_node("getContext", get_context_summary) # Optional: for deeper context
workflow.add_node("extractDetails", extract_interaction_details)
workflow.add_node("conversationalAgent", conversational_agent_node)

# Define edges
# workflow.set_entry_point("getContext") # If using context summarization first
# workflow.add_edge("getContext", "extractDetails")
workflow.set_entry_point("extractDetails") # Start directly with extraction for simpler flow
workflow.add_edge("extractDetails", "conversationalAgent")
workflow.add_edge("conversationalAgent", END) # For now, simple flow. Could loop or go to human validation.


# Compile the graph
app_graph = workflow.compile()


# --- FastAPI Integration (Example) ---
# This part would typically be in your main.py or a dedicated routes file.
# For simplicity, including a function here that could be called by FastAPI.

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = [] # e.g., [{'type': 'human', 'content': 'Hi'}, {'type': 'ai', 'content': 'Hello!'}]

async def process_chat_message(request: ChatRequest):
    """
    Processes a chat message using the LangGraph agent.
    This function would be called by your FastAPI endpoint for /api/chat_interaction
    """
    logger.info(f"Processing chat message: {request.message}")

    # Convert history to BaseMessage objects
    langchain_history = []
    for msg in request.history:
        if msg.get("sender") == "user" or msg.get("type") == "human": # Adapt based on frontend message format
            langchain_history.append(HumanMessage(content=msg.get("text") or msg.get("content")))
        elif msg.get("sender") == "ai" or msg.get("type") == "ai":
            langchain_history.append(AIMessage(content=msg.get("text") or msg.get("content")))

    initial_state: InteractionState = {
        "messages": langchain_history,
        "user_input": request.message,
        "extracted_data": None,
        "context_summary": None,
    }

    # Invoke the graph. Stream or full response depends on your preference.
    # For a chat, you often want the final AI message and any extracted data.
    final_state = None
    async for event_output in app_graph.astream(initial_state):
        # astream returns all node outputs. We are interested in the final state or specific node outputs.
        # logger.info(f"Graph event: {event_output}")
        for key, value in event_output.items(): # `key` is the node name
            logger.info(f"Output from node '{key}': {value}")
            if key == "extractDetails":
                initial_state["extracted_data"] = value.get("extracted_data")
            if key == "conversationalAgent": # This is the last node in this simple setup
                final_state = value # Contains the AI's response message
                # We might also want to update overall state with this message
                if "messages" in value and value["messages"]:
                    # Assuming value["messages"] is a list of new messages from this node
                    new_ai_message_obj = value["messages"][-1] # Get the last AI message from the node
                    initial_state["messages"].append(HumanMessage(content=request.message)) # User's trigger message
                    initial_state["messages"].append(new_ai_message_obj) # AI's response


    # The AI's reply for the chat interface
    ai_reply_content = "Sorry, I couldn't generate a response."
    if final_state and "messages" in final_state and final_state["messages"]:
        # Assuming the last message from 'conversationalAgent' node is the one to send back
        ai_reply_content = final_state["messages"][-1].content


    # Extracted data to potentially pre-fill form or save directly
    extracted_json = None
    if initial_state["extracted_data"]:
        # Convert Pydantic model to dict, handling potential list for productsDiscussed
        extracted_dict = initial_state["extracted_data"].model_dump()
        if extracted_dict.get("productsDiscussed") and isinstance(extracted_dict["productsDiscussed"], list):
            extracted_dict["productsDiscussed"] = ", ".join(extracted_dict["productsDiscussed"])
        extracted_json = extracted_dict


    logger.info(f"Final AI reply: {ai_reply_content}, Extracted data: {extracted_json}")

    return {"reply": ai_reply_content, "extracted_data": extracted_json}


# Example usage (for testing this file directly):
async def main_test():
    if GROQ_API_KEY == "YOUR_GROQ_API_KEY_PLACEHOLDER":
        print("WARNING: GROQ_API_KEY is not set. Agent calls will fail.")
        print("Please set the GROQ_API_KEY environment variable or replace the placeholder in the script.")
        # return

    # Simulate a chat request
    test_request_1 = ChatRequest(message="Logged a meeting with Dr. Smith yesterday about ProductA and ProductB. Key takeaway was positive feedback on ProductA's dosage.")
    response_1 = await process_chat_message(test_request_1)
    print("\n--- Test Response 1 ---")
    print(f"AI Reply: {response_1['reply']}")
    print(f"Extracted Data: {json.dumps(response_1['extracted_data'], indent=2)}")

    test_request_2 = ChatRequest(
        message="What about follow up actions?",
        history=[
            {"sender": "user", "text": "Logged a meeting with Dr. Smith yesterday about ProductA and ProductB. Key takeaway was positive feedback on ProductA's dosage."},
            {"sender": "ai", "text": response_1['reply'], "extractedData": response_1['extracted_data']}
        ]
    )
    response_2 = await process_chat_message(test_request_2)
    print("\n--- Test Response 2 ---")
    print(f"AI Reply: {response_2['reply']}")
    print(f"Extracted Data: {json.dumps(response_2['extracted_data'], indent=2)}")

    test_request_3 = ChatRequest(
        message="Yes, need to send him the latest ProductA study results by Friday.",
         history=[
            {"sender": "user", "text": "Logged a meeting with Dr. Smith yesterday about ProductA and ProductB. Key takeaway was positive feedback on ProductA's dosage."},
            {"sender": "ai", "text": response_1['reply'], "extractedData": response_1['extracted_data']},
            {"sender": "user", "text": "What about follow up actions?"},
            {"sender": "ai", "text": response_2['reply'], "extractedData": response_2['extracted_data']}
        ]
    )
    response_3 = await process_chat_message(test_request_3)
    print("\n--- Test Response 3 ---")
    print(f"AI Reply: {response_3['reply']}")
    print(f"Extracted Data: {json.dumps(response_3['extracted_data'], indent=2)}")


if __name__ == "__main__":
    import asyncio
    # To run this test: python ai_agent.py
    # Ensure you have GROQ_API_KEY set as an environment variable.
    # You might need to install packages: pip install langgraph langchain-core langchain-groq pydantic uvicorn fastapi
    asyncio.run(main_test())

# To integrate with FastAPI (in main.py or similar):
# from ai_agent import process_chat_message, ChatRequest
#
# @app.post("/api/chat_interaction") # This would be in your main FastAPI app file
# async def chat_handler(request: ChatRequest):
#     try:
#         result = await process_chat_message(request)
#         return result
#     except Exception as e:
#         logger.error(f"Error in chat_handler: {e}")
#         raise HTTPException(status_code=500, detail=str(e))