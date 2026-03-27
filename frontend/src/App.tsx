import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, MicOff, PhoneCall, Activity, Volume2, Languages } from 'lucide-react';

// Extend Window for webkitSpeechRecognition
declare global {
  interface Window {
    webkitSpeechRecognition: any;
    SpeechRecognition: any;
  }
}

interface TraceLog {
  time: string;
  message: string;
  type: 'info' | 'tool' | 'response' | 'error';
}

export default function App() {
  const [isListening, setIsListening] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [logs, setLogs] = useState<TraceLog[]>([]);
  const [latency, setLatency] = useState<number | null>(null);
  const [transcript, setTranscript] = useState('');
  const [agentText, setAgentText] = useState('');
  const [selectedLang, setSelectedLang] = useState('en-IN');

  const wsRef = useRef<WebSocket | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const selectedLangRef = useRef(selectedLang);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => { selectedLangRef.current = selectedLang; }, [selectedLang]);

  const addLog = useCallback((message: string, type: TraceLog['type'] = 'info') => {
    setLogs(prev => [...prev, {
      time: new Date().toLocaleTimeString(),
      message,
      type
    }]);
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Play base64-encoded MP3 audio from the server
  const playAudio = useCallback((audioBase64: string) => {
    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    try {
      const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
      audioRef.current = audio;

      audio.onplay = () => {
        console.log('[Audio] Playback started');
        setIsSpeaking(true);
      };
      audio.onended = () => {
        console.log('[Audio] Playback ended');
        setIsSpeaking(false);
        audioRef.current = null;
      };
      audio.onerror = (e) => {
        console.error('[Audio] Playback error:', e);
        setIsSpeaking(false);
        audioRef.current = null;
      };

      audio.play().catch(err => {
        console.error('[Audio] Play failed:', err);
        setIsSpeaking(false);
      });
    } catch (err) {
      console.error('[Audio] Failed to create audio:', err);
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket('ws://localhost:8000/ws/voice');

    ws.onopen = () => {
      setIsConnected(true);
      addLog('WebSocket connected to backend', 'info');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'session.created') {
          addLog(`Session started: ${data.session_id}`, 'info');
        }

        if (data.type === 'trace') {
          const isToolTrace = data.event.includes('Tool');
          addLog(data.event, isToolTrace ? 'tool' : 'info');
        }

        if (data.type === 'agent.response') {
          // Safety net: strip any leaked function XML from agent response
          const cleanText = (data.text || '')
            .replace(/<function=\w+>.*?<\/function>/gs, '')
            .replace(/<\/?function[^>]*>/g, '')
            .replace(/\s{2,}/g, ' ')
            .trim();

          setAgentText(cleanText);
          setLatency(data.latency_ms);
          addLog(`Agent: "${cleanText.substring(0, 80)}..."`, 'response');
        }

        // Play server-generated TTS audio
        if (data.type === 'agent.audio' && data.audio) {
          console.log('[Audio] Received server TTS audio, playing...');
          addLog('Playing agent audio...', 'info');
          playAudio(data.audio);
        }
      } catch (e) { /* ignore */ }
    };

    ws.onclose = () => {
      setIsConnected(false);
      addLog('WebSocket disconnected', 'error');
    };

    ws.onerror = () => {
      addLog('WebSocket error — is the backend running?', 'error');
    };

    wsRef.current = ws;
  }, [addLog, playAudio]);



  const startListening = useCallback(() => {
    connectWebSocket();

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      addLog('Speech Recognition not supported in this browser', 'error');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = selectedLang;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }

      setTranscript(interimTranscript || finalTranscript);

      if (finalTranscript.trim()) {
        // Barge-in: stop agent audio if user starts talking
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current = null;
        }
        setIsSpeaking(false);

        // Send final transcript to backend with language preference
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'user.message',
            text: finalTranscript.trim(),
            lang: selectedLangRef.current
          }));
        }
        setTranscript('');
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onerror = (event: any) => {
      addLog(`Speech recognition error: ${event.error}`, 'error');
    };

    recognition.start();
    recognitionRef.current = recognition;
    setIsListening(true);
    addLog(`Listening in ${selectedLang === 'hi-IN' ? 'Hindi' : selectedLang === 'ta-IN' ? 'Tamil' : 'English'}...`, 'info');
  }, [connectWebSocket, addLog, selectedLang]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setIsListening(false);
    setIsSpeaking(false);
    addLog('Stopped listening', 'info');
  }, [addLog]);

  const langOptions = [
    { code: 'en-IN', label: 'English', flag: '🇬🇧' },
    { code: 'hi-IN', label: 'Hindi', flag: '🇮🇳' },
    { code: 'ta-IN', label: 'Tamil', flag: '🇮🇳' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-blue-950 text-white flex flex-col items-center py-10 font-sans">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-5xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-cyan-400 to-emerald-400 flex items-center gap-3 justify-center">
          <PhoneCall className="w-10 h-10 text-blue-400" />
          2Care Voice Agent
        </h1>
        <p className="text-gray-400 mt-3 max-w-lg mx-auto text-lg">
          Real-time multilingual clinical appointment scheduling
        </p>
      </div>

      {/* Language Selector */}
      <div className="mt-8 flex items-center gap-3">
        <Languages className="w-5 h-5 text-gray-400" />
        {langOptions.map(lang => (
          <button
            key={lang.code}
            onClick={() => setSelectedLang(lang.code)}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${selectedLang === lang.code
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
          >
            {lang.flag} {lang.label}
          </button>
        ))}
      </div>

      {/* Main Call Button */}
      <div className="mt-8">
        <button
          onClick={isListening ? stopListening : startListening}
          className={`flex items-center gap-3 px-10 py-5 rounded-full text-lg font-bold transition-all duration-300 shadow-2xl ${isListening
            ? 'bg-red-500 hover:bg-red-600 shadow-red-500/40 animate-pulse'
            : 'bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-700 hover:to-cyan-600 shadow-blue-500/40'
            }`}
        >
          {isListening ? <><MicOff className="w-6 h-6" /> End Call</> : <><Mic className="w-6 h-6" /> Start Call</>}
        </button>
      </div>

      {/* Live Transcript */}
      {(transcript || agentText) && (
        <div className="mt-6 w-full max-w-2xl px-4">
          {transcript && (
            <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-4 mb-3">
              <span className="text-xs text-gray-500 uppercase tracking-wider">You are saying:</span>
              <p className="text-white text-lg mt-1 italic">"{transcript}"</p>
            </div>
          )}
          {agentText && (
            <div className="bg-blue-900/30 border border-blue-800/50 rounded-xl p-4 flex items-start gap-3">
              <Volume2 className={`w-5 h-5 mt-1 ${isSpeaking ? 'text-emerald-400 animate-pulse' : 'text-gray-500'}`} />
              <div>
                <span className="text-xs text-blue-400 uppercase tracking-wider">Agent Response:</span>
                <p className="text-gray-200 text-base mt-1">{agentText}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Stats & Traces Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-10 w-full max-w-5xl px-4">
        {/* Latency Panel */}
        <div className="bg-gray-900/80 backdrop-blur border border-gray-800 rounded-2xl p-6">
          <h2 className="text-xl font-bold text-gray-200 mb-4 flex items-center gap-2">
            <Activity className="text-emerald-400" />
            Pipeline Latency
          </h2>
          <div className="flex flex-col gap-3">
            <div className="flex justify-between items-center bg-gray-800/60 p-4 rounded-xl">
              <span className="text-gray-400">Target</span>
              <span className="text-emerald-400 font-mono font-bold">&lt; 450 ms</span>
            </div>
            <div className="flex justify-between items-center bg-gray-800/60 p-4 rounded-xl">
              <span className="text-gray-400">Measured (LLM round-trip)</span>
              <span className={`font-mono font-bold ${latency && latency < 450 ? 'text-emerald-400' : latency ? 'text-red-400' : 'text-gray-500'}`}>
                {latency ? `${latency} ms` : '--'}
              </span>
            </div>
            <div className="flex justify-between items-center bg-gray-800/60 p-4 rounded-xl">
              <span className="text-gray-400">Status</span>
              <span className={`font-semibold ${isConnected ? 'text-emerald-400' : 'text-gray-500'}`}>
                {isConnected ? '● Connected' : '○ Disconnected'}
              </span>
            </div>
          </div>
        </div>

        {/* Reasoning Traces */}
        <div className="bg-gray-900/80 backdrop-blur border border-gray-800 rounded-2xl p-6 flex flex-col h-96">
          <h2 className="text-xl font-bold text-gray-200 mb-4">Reasoning Trace & Events</h2>
          <div className="flex-1 overflow-y-auto font-mono text-xs flex flex-col gap-1.5 pr-2">
            {logs.length === 0 && <span className="text-gray-600">Waiting for events...</span>}
            {logs.map((log, i) => (
              <div key={i} className={`leading-relaxed ${log.type === 'tool' ? 'text-amber-400' :
                log.type === 'response' ? 'text-cyan-400' :
                  log.type === 'error' ? 'text-red-400' :
                    'text-emerald-400'
                }`}>
                <span className="text-gray-600">[{log.time}]</span> {log.message}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
