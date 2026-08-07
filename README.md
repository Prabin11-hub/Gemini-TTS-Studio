# Gemini TTS Studio

A local, production-ready desktop application (Windows 11, Python 3.13) that
converts `.txt` files into natural AI-generated speech using Google's Gemini
text-to-speech model, via the `google-genai` SDK's Interactions API.

## Features

- Generate speech from a single text file, or batch-process every `.txt`
  file in `input/`.
- Output filename always matches the input filename (`book1.txt` -> `book1.wav`).
- Long scripts are automatically split into safe chunks and the resulting
  audio is stitched into **one** final `.wav` file — never dozens of files.
- Streaming generation with a live progress bar.
- Automatic retry with exponential backoff on transient API failures.
- Friendly, human-readable error messages.
- Automatic creation of `input/`, `output/`, and `logs/` folders.
- Full Unicode support, including Hindi and English, in the same run.
- Structured logging to `logs/app.log` (timestamp, filename, duration, status).
- Voice and style ("Director's Notes") presets in `config/voices.json`.

## Project structure

```
Gemini-TTS/
├── input/              # Source .txt files to convert
│   ├── script.txt
│   ├── video1.txt
│   └── video2.txt
├── output/              # Generated .wav files land here
├── config/
│   └── voices.json       # Named voice/style presets
├── logs/
│   └── app.log            # Created automatically on first run
├── src/
│   ├── config.py          # Centralized app configuration
│   ├── tts.py               # Gemini TTS client (chunking, retry, streaming)
│   ├── batch.py              # Batch processing over input/
│   ├── main.py                 # CLI entry point / menu
│   ├── utils.py                  # File, folder, audio, and validation helpers
│   ├── logger.py                    # Logging setup
│   └── exceptions.py                  # Custom exception hierarchy
├── .env.example
├── requirements.txt
└── README.md
```

## Installation

1. Install **Python 3.13** on Windows 11.
2. Open a terminal in the `Gemini-TTS` folder.
3. Create and activate a virtual environment (recommended):

   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

## API key setup

1. Get a Gemini API key from <https://aistudio.google.com/apikey>.
2. Copy `.env.example` to `.env`:

   ```powershell
   copy .env.example .env
   ```

3. Open `.env` and set:

   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

You can also adjust the model, default voice, retry policy, and chunk size
in the same `.env` file — no code changes required.

## Usage

Run the app from the project root:

```powershell
python src/main.py
```

You'll see:

```
----------------------------------
Gemini TTS Studio
----------------------------------

Active voice: Kore
1. Generate one file
2. Batch generate
3. Change voice
4. Exit

Choice:
```

### 1. Generate one file

Enter a filename that exists in `input/`, e.g. `book1.txt`. The app reads
`input/book1.txt` and writes `output/book1.wav`.

### 2. Batch generate

Automatically processes every `.txt` file found in `input/`, showing progress
per file and a final success/failure summary.

### 3. Change voice

Choose a named preset from `config/voices.json` (e.g. `Commercial`, `Story`,
`Podcast`, `Narration`, `Motivational`, `Audiobook`, `Documentary`,
`Conversation`), or type any raw Gemini voice name (e.g. `Algieba`, `Zephyr`,
`Puck`). The choice applies to all generations for the rest of the session.

### 4. Exit

Closes the application.

## Voice presets (`config/voices.json`)

Each preset defines a `voice_name` and `director_notes` (a short natural-
language style instruction sent to the model alongside your transcript).
Add, remove, or edit presets freely — no code changes required.

```json
{
  "Commercial": {
    "voice_name": "Puck",
    "description": "Upbeat, energetic voice suited for ads and promos.",
    "director_notes": "Style: Enthusiastic and persuasive commercial announcer..."
  }
}
```

## How long scripts are handled

Gemini TTS has a 32k-token context window, and speech quality can drift on
very long single generations. Gemini TTS Studio automatically splits long
text on sentence boundaries into chunks (configurable via `MAX_CHUNK_CHARS`
in `.env`), generates audio for each chunk, and concatenates the raw audio
in memory before writing **one** final `.wav` file. No intermediate files
are ever created.

## Troubleshooting

| Problem                                          | Cause                                                                                                          | Fix                                                                                   |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `Configuration error: GEMINI_API_KEY is not set` | Missing/empty `.env`                                                                                           | Copy `.env.example` to `.env` and add your key                                        |
| `Input file not found`                           | File missing from `input/`                                                                                     | Check the filename and that it's inside `input/`                                      |
| `'<file>' is not valid UTF-8 text`               | File saved with wrong encoding                                                                                 | Re-save the file as UTF-8                                                             |
| Repeated retries then failure                    | Network issue or the model occasionally returns text instead of audio (a documented, rare Gemini TTS behavior) | The app already retries automatically; try again, or increase `RETRY_COUNT` in `.env` |
| Audio cuts off oddly for very long files         | Chunk boundaries mid-sentence                                                                                  | Lower `MAX_CHUNK_CHARS` in `.env` for shorter, cleaner chunks                         |
| `No .txt files found in 'input'`                 | Input folder empty                                                                                             | Add `.txt` files to `input/`                                                          |

Logs for every run are written to `logs/app.log` (timestamp, filename,
duration, status, and any error) and rotate automatically once they exceed
5 MB.

## Notes on the Gemini API

This project uses Google's `google-genai` Python SDK **Interactions API**
(`client.interactions.create(...)`), the current officially documented way
to call Gemini TTS models such as `gemini-3.1-flash-tts-preview`. Streaming
is used so the app can report generation progress as audio arrives.
