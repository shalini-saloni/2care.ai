# 2Care Clinical Voice AI Agent

A real-time, multilingual (English, Hindi, Tamil) conversational AI agent designed to handle inbound and outbound clinical appointment scheduling.

## Features
- **Real-time Voice Voice**: Sub-450ms latency using OpenAI Realtime WebSocket integration.
- **Multilingual Support**: Supports English, Hindi, and Tamil organically.
- **Contextual Memory**: Redis-backed session state (TTL based) and SQLite-backed persistent patient tracking.
- **Conflict Management**: Guaranteed protection against double-bookings via DB transaction locks.
- **Outbound Campaigns**: API-driven background jobs to simulate reminder and follow-up outbound calls.

## Architecture

- **Frontend**: Vite + React + TS handling PCM16 audio encoding and chunk streaming via standard WebSockets.
- **Backend**: FastAPI WebSockets managing connections.
- **State**: SQLite (persistent storage) and Redis (ephemeral in-flight context).
- **Core Engine**: OpenAI Realtime API (`gpt-4o-realtime-preview`) native engine supporting tools (`book_appointment`, `check_availability`).

## Latency Breakdown & Target

Our goal was **< 450 ms end-to-end**.
1. **Network Trip (Frontend > Backend)**: ~20ms
2. **Backend to Engine**: ~30ms
3. **OpenAI Realtime Reasoning & TTS generation (Model streaming response delay)**: ~200-300ms
4. **Tool Execution (if invoked)**: ~10ms (SQLite query)
5. **Network Trip (Backend > Frontend)**: ~20ms

*Total Estimated Latency from Speech End to Audio First Byte*: **~300-380 ms**.

## Setup & Running locally
1. Install dependencies for Backend (`cd backend && pip install -r requirements.txt`)
2. Export `OPENAI_API_KEY=your_key`
3. Run Backend: `uvicorn app.main:app --reload --port 8000`
4. Set up Frontend (`cd frontend && npm i`)
5. Run Frontend: `npm run dev`

## Known Limitations & Tradeoffs
- **Realtime API Dependence**: For the purposes of achieving ultra-low latency (<450ms) with multiple languages, using a unified engine (GPT-4o Realtime) is computationally faster than chaining separate ASR -> LLM -> TTS services. The tradeoff is vendor lock-in and cost.
- **Mock Audio Player**: Safari compatibility for PCM 16 chunked streaming over WebSockets usually requires a dedicated `AudioWorklet`. The frontend provides standard base64 chunk delivery for verification.
- **Local SQLite DB**: Used for simplified environment setup; replace with PostgreSQL for horizontal scalability.
