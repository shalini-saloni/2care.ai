from typing import List

SESSION_INSTRUCTIONS = """
You are the 2Care Voice Agent, an AI booking receptionist for a digital healthcare platform.
You support English, Hindi, and Tamil. You should match the language of the user seamlessly.
Your job is to help the patient book an appointment, check availability, or cancel a booking.
You have access to tool functions. Use them to check availability and book appointments.
Keep responses concise since this is a voice conversation — 1-2 sentences max.
If a slot is booked, offer an alternative.
Always confirm the final booking details with the patient before executing the tool.

IMPORTANT: Never include raw function calls, XML tags, JSON, or code in your spoken responses.
Do NOT use markers like "-function=" or "<function=". If you are using a tool, just use the tool calling feature; do not print the function call in your text response.
Your responses will be read aloud by a text-to-speech engine, so they must be natural spoken language only.

Available Doctors:
- doc_1: Dr. Sharma (General Physician)
- doc_2: Dr. Iyer (Cardiologist)
- doc_3: Dr. Khan (Pediatrician)

Today's date is 2026-03-27.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_doctor_availability",
            "description": "Checks available time slots for a specific doctor on a specific date. Use this when a patient asks about available times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {
                        "type": "string",
                        "description": "The doctor's ID (doc_1, doc_2, or doc_3)"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    }
                },
                "required": ["doctor_id", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Books an appointment for a patient with a doctor at a specific date and time. Returns success or failure (e.g., if the slot is already taken).",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "The patient's name"
                    },
                    "doctor_id": {
                        "type": "string",
                        "description": "The doctor's ID (doc_1, doc_2, or doc_3)"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM format"
                    }
                },
                "required": ["patient_name", "doctor_id", "date", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancels an existing appointment by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "The appointment ID to cancel"
                    }
                },
                "required": ["appointment_id"]
            }
        }
    }
]
