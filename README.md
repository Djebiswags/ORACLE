# ORACLE
A personal AI assistant that runs on Android in Termux.
Python + Gemini API with function calling: Google Search grounding, SMS, contacts,
notifications, reminders, battery, clipboard, voice input/TTS, persistent memory,
and shell commands behind a confirmation step.

## Setup
pkg install python termux-api
pip install google-genai
export GEMINI_API_KEY=your_key
python assistant.py
