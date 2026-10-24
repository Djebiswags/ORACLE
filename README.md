# ORACLE

A personal AI assistant that runs entirely on an Android phone in Termux.

Built in Python on the Gemini API with function calling. ORACLE decides which tool to use and chains them together:

- Web search with Google Search grounding
- Read and send SMS, look up contacts
- Read notifications, battery status, clipboard
- Timed reminders
- Voice input and spoken replies (TTS)
- Persistent memory and conversation history
- Shell commands, only after the user confirms

I talk to it daily in English and Nigerian Pidgin.

## Setup

```bash
pkg install python termux-api
export GEMINI_API_KEY=your_key
python assistant.py
```

Install the Termux:API app from F-Droid for SMS, contacts, voice and notifications.
