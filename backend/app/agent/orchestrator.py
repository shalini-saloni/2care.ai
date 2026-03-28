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
    """Strip leaked function-call artifacts from LLM text output.
    
    Llama models sometimes embed raw function tags or custom markers like:
      -function=book_appointment>{"date":"..."}
      <function=book_appointment>...</function>
    This must be removed before displaying or speaking the response.
    """
    
    text = re.sub(r'[-<]function=\w+>.*?(?:</function>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    text = re.sub(r'</?function[^>]*>', '', text, flags=re.IGNORECASE)
    
    text = re.sub(r'^\s*\{".*?"\s*:\s*".*?"\}\s*$', '', text, flags=re.MULTILINE)

    text = re.sub(r'[*#_]+', '', text)
    
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

logger = logging.getLogger(__name__)

def get_groq_client():
    """Lazy initialization so .env changes are picked up on reload."""
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set! Please update backend/.env with your real key.")
    return Groq(api_key=api_key)

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
    session_lang = "en"  
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

                max_iterations = 5
                for iteration in range(max_iterations):
                    try:
                        stream = get_groq_client().chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=sessions[session_id],
                            tools=TOOLS,
                            tool_choice="auto",
                            max_tokens=300,
                            stream=True
                        )
                        
                        full_content = ""
                        tool_calls = {} 
                        finish_reason = None
                        
                        for chunk in stream:
                            if not chunk.choices:
                                continue
                            
                            delta = chunk.choices[0].delta
                            finish_reason = chunk.choices[0].finish_reason
                            
                            if delta.content:
                                content = delta.content
                                full_content += content
                                
                                await websocket.send_text(json.dumps({
                                    "type": "agent.response_chunk",
                                    "text": content
                                }))
                            
                            if delta.tool_calls:
                                for tc_chunk in delta.tool_calls:
                                    idx = tc_chunk.index
                                    if idx not in tool_calls:
                                        tool_calls[idx] = tc_chunk
                                    else:
                                        if tc_chunk.function.arguments:
                                            if not tool_calls[idx].function.arguments:
                                                tool_calls[idx].function.arguments = ""
                                            tool_calls[idx].function.arguments += tc_chunk.function.arguments
                        
                        if tool_calls:
                            tc_list = list(tool_calls.values())
                            
                            assistant_msg = {"role": "assistant", "tool_calls": []}
                            for tc in tc_list:
                                assistant_msg["tool_calls"].append({
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments
                                    }
                                })
                            
                            sessions[session_id].append(assistant_msg)
                            
                            for tc in assistant_msg["tool_calls"]:
                                fn_name = tc["function"]["name"]
                                fn_args_raw = tc["function"]["arguments"]
                                try:
                                    fn_args = json.loads(fn_args_raw)
                                except json.JSONDecodeError:
                                    logger.warning(f"Malformed tool args: {fn_args_raw}")
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
                                    "tool_call_id": tc["id"],
                                    "content": result
                                })
                            continue
                            
                        else:
                            assistant_text = clean_agent_response(full_content)
                            sessions[session_id].append({"role": "assistant", "content": assistant_text})

                            t_end = time.time()
                            latency_ms = round((t_end - t_start) * 1000)
                            logger.info(f"Response latency: {latency_ms}ms")

                            await websocket.send_text(json.dumps({
                                "type": "agent.response",
                                "text": assistant_text,
                                "latency_ms": latency_ms
                            }))

                            try:
                                audio_b64 = text_to_speech_base64(assistant_text, session_lang)
                                if audio_b64:
                                    await websocket.send_text(json.dumps({
                                        "type": "agent.audio",
                                        "audio": audio_b64,
                                        "format": "mp3"
                                    }))
                            except Exception as tts_err:
                                logger.error(f"TTS error: {tts_err}")

                            await websocket.send_text(json.dumps({
                                "type": "trace",
                                "event": f"Agent responded in {latency_ms}ms"
                            }))
                            break

                    except Exception as api_err:
                        logger.info(f"Retrying with Groq...") 
                        logger.error(f"Error in Groq streaming: {api_err}", exc_info=True)
                        await websocket.send_text(json.dumps({
                            "type": "agent.response",
                            "text": "I'm sorry, I encountered an error. Could you repeat that?",
                            "latency_ms": 0
                        }))
                        break

    except WebSocketDisconnect:
        logger.info(f"Client disconnected. Session: {session_id}")
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
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
