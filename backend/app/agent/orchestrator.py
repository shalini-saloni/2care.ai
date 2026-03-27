import json
import logging
import re
import time
import uuid
from groq import Groq
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.agent.tools import TOOLS, SESSION_INSTRUCTIONS
from app.agent.tts import text_to_speech_base64
from app.db.dal import db


def clean_agent_response(text: str) -> str:
    """Strip leaked function-call XML and other artifacts from LLM text output.
    
    Llama 3.3 sometimes embeds raw function tags like:
      <function=book_appointment>{"date":"2026-03-27",...}</function>
    This must be removed before displaying or speaking the response.
    """
    # Remove <function=...>...</function> blocks
    text = re.sub(r'<function=\w+>.*?</function>', '', text, flags=re.DOTALL)
    # Remove any remaining lone <function> or </function> tags
    text = re.sub(r'</?function[^>]*>', '', text)
    # Remove markdown bold/italic/headers
    text = re.sub(r'[*#_]+', '', text)
    # Clean up extra whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text

logger = logging.getLogger(__name__)

def get_groq_client():
    """Lazy initialization so .env changes are picked up on reload."""
    api_key = settings.GROQ_API_KEY
    if not api_key or api_key == "your-groq-api-key-here":
        raise ValueError("GROQ_API_KEY is not set! Please update backend/.env with your real key.")
    return Groq(api_key=api_key)

# Per-session conversation history (in-memory, keyed by session)
sessions: dict[str, list] = {}

def execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the result as a string."""
    logger.info(f"Executing tool: {name} with args: {args}")

    if name == "check_doctor_availability":
        slots = db.get_doctor_availability(args["doctor_id"], args["date"])
        return json.dumps({"available_slots": slots, "doctor_id": args["doctor_id"]})

    elif name == "book_appointment":
        apt_id = str(uuid.uuid4())[:8]
        patient_id = str(uuid.uuid4())[:8]
        success, msg = db.book_appointment(
            apt_id, patient_id,
            args["doctor_id"], args["date"], args["time"]
        )
        return json.dumps({"success": success, "message": msg, "appointment_id": apt_id if success else None})

    elif name == "cancel_appointment":
        success = db.cancel_appointment(args["appointment_id"])
        return json.dumps({"success": success})

    return json.dumps({"error": "Unknown tool"})


async def handle_websocket_connection(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    sessions[session_id] = [{"role": "system", "content": SESSION_INSTRUCTIONS}]
    session_lang = "en"  # Track user's language preference
    logger.info(f"Client connected. Session: {session_id}")

    await websocket.send_text(json.dumps({
        "type": "session.created",
        "session_id": session_id
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data.get("type") == "user.message":
                user_text = data.get("text", "")
                # Track language preference from frontend
                if data.get("lang"):
                    lang_code = data["lang"]
                    if lang_code.startswith("hi"):
                        session_lang = "hi"
                    elif lang_code.startswith("ta"):
                        session_lang = "ta"
                    else:
                        session_lang = "en"
                if not user_text.strip():
                    continue

                t_start = time.time()

                sessions[session_id].append({"role": "user", "content": user_text})

                await websocket.send_text(json.dumps({
                    "type": "trace",
                    "event": f'User said: "{user_text}"'
                }))

                # Call Groq with tool support — loop until final text response
                max_iterations = 5
                for iteration in range(max_iterations):
                    try:
                        response = get_groq_client().chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=sessions[session_id],
                            tools=TOOLS,
                            tool_choice="auto",
                            max_tokens=300,
                        )
                    except Exception as api_err:
                        # Handle Groq tool_use_failed or other API errors gracefully
                        logger.warning(f"Groq API error (attempt {iteration+1}): {api_err}")
                        await websocket.send_text(json.dumps({
                            "type": "trace",
                            "event": f"Tool call error, retrying without tools..."
                        }))
                        # Retry without tools as fallback
                        try:
                            response = get_groq_client().chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=sessions[session_id],
                                max_tokens=300,
                            )
                        except Exception as fallback_err:
                            logger.error(f"Fallback also failed: {fallback_err}")
                            await websocket.send_text(json.dumps({
                                "type": "agent.response",
                                "text": "I'm sorry, I encountered a technical issue. Could you please repeat that?",
                                "latency_ms": round((time.time() - t_start) * 1000)
                            }))
                            break

                    choice = response.choices[0]

                    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                        # Append assistant message with tool calls
                        sessions[session_id].append(choice.message)

                        for tool_call in choice.message.tool_calls:
                            fn_name = tool_call.function.name
                            try:
                                fn_args = json.loads(tool_call.function.arguments)
                            except json.JSONDecodeError:
                                logger.warning(f"Malformed tool args: {tool_call.function.arguments}")
                                fn_args = {}

                            await websocket.send_text(json.dumps({
                                "type": "trace",
                                "event": f"Tool called: {fn_name}({json.dumps(fn_args)})"
                            }))

                            result = execute_tool(fn_name, fn_args)

                            await websocket.send_text(json.dumps({
                                "type": "trace",
                                "event": f"Tool result: {result}"
                            }))

                            sessions[session_id].append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result
                            })
                    else:
                        # Final text response
                        raw_text = choice.message.content or ""
                        assistant_text = clean_agent_response(raw_text)
                        logger.info(f"Raw LLM output: {raw_text}")
                        logger.info(f"Cleaned output: {assistant_text}")
                        sessions[session_id].append({"role": "assistant", "content": assistant_text})

                        t_end = time.time()
                        latency_ms = round((t_end - t_start) * 1000)
                        logger.info(f"Response latency: {latency_ms}ms")

                        await websocket.send_text(json.dumps({
                            "type": "agent.response",
                            "text": assistant_text,
                            "latency_ms": latency_ms
                        }))

                        # Generate TTS audio on the server and send it
                        try:
                            audio_b64 = text_to_speech_base64(assistant_text, session_lang)
                            if audio_b64:
                                await websocket.send_text(json.dumps({
                                    "type": "agent.audio",
                                    "audio": audio_b64,
                                    "format": "mp3"
                                }))
                                logger.info(f"TTS audio sent ({len(audio_b64)} chars base64)")
                            else:
                                logger.warning("TTS returned no audio")
                        except Exception as tts_err:
                            logger.error(f"TTS error: {tts_err}")

                        await websocket.send_text(json.dumps({
                            "type": "trace",
                            "event": f"Agent responded in {latency_ms}ms"
                        }))
                        break

    except WebSocketDisconnect:
        logger.info(f"Client disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        # Send error to client instead of crashing
        try:
            await websocket.send_text(json.dumps({
                "type": "agent.response",
                "text": "Sorry, an error occurred. Please try again.",
                "latency_ms": 0
            }))
        except:
            pass
    finally:
        sessions.pop(session_id, None)
        try:
            await websocket.close()
        except:
            pass
