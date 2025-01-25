from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import google.generativeai as genai
import random
from TTS.api import TTS
import os
import time
from pydub import AudioSegment
from tqdm import tqdm
from datetime import datetime
import json
from pathlib import Path

app = FastAPI()

# Statische Dateien für Downloads
app.mount("/output", StaticFiles(directory="output"), name="output")

# HTML Template für die UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Audio Generator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            text-align: center;
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            margin: 10px;
        }
        button:disabled {
            background-color: #cccccc;
        }
        #status {
            margin: 20px 0;
        }
        #generatedText {
            margin: 20px 0;
            padding: 20px;
            background-color: #f0f0f0;
            border-radius: 4px;
            text-align: left;
            white-space: pre-wrap;
            display: none;
        }
        #downloadLink {
            display: none;
            margin: 20px 0;
            padding: 10px;
            background-color: #e0e0e0;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <h1>Audio Generator</h1>
    <button id="generateBtn" onclick="generateAudio()">Generate Audio</button>
    <div id="status"></div>
    <div id="generatedText"></div>
    <div id="downloadLink"></div>

    <script>
        async function generateAudio() {
            const button = document.getElementById('generateBtn');
            const status = document.getElementById('status');
            const textDiv = document.getElementById('generatedText');
            const downloadLink = document.getElementById('downloadLink');
            
            button.disabled = true;
            status.textContent = 'Generating audio...';
            textDiv.style.display = 'none';
            downloadLink.style.display = 'none';
            
            try {
                const response = await fetch('/generate', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    throw new Error('Generation failed');
                }
                
                const data = await response.json();
                status.textContent = 'Audio generated successfully!';
                textDiv.textContent = data.text;
                textDiv.style.display = 'block';
                downloadLink.innerHTML = `<a href="${data.file_path}" download>Download Audio</a>`;
                downloadLink.style.display = 'block';
            } catch (error) {
                status.textContent = 'Error generating audio. Please try again.';
            } finally {
                button.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

class Config:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "gemini_api_key": "AIzaSyApi6I9YbQxn81NejAciuw3N3HNEunJQgU",
                "output_dir": "output",
                "tts_model": "tts_models/en/vctk/vits",
                "tts_speaker": "p230",
                "max_retries": 3
            }
            self.save_config(config)
        
        for key, value in config.items():
            setattr(self, key, value)

    def save_config(self, config):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=4)

class ContentGenerator:
    def __init__(self, config):
        self.config = config
        genai.configure(api_key=config.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.seed = random.randint(1, 1000000000)

    def generate_prompt(self):
        return f"""
        Hook: Question, What would happen if.

        Create an engaging analysis of this hypothetical scenario:
        - What are the consequences and effects of this scenario?
        - What are the pros and cons of this scenario?
        - Who would be affected by this scenario?
        - Will a war break out?

        Answer in English and structure the response to be approximately 1 minute when spoken.
        Use seed {self.seed} to ensure response variation.
        Make it engaging and thought-provoking for listeners.
        Simple and short sentences.
        A major Keyword in every sentence between ()
        """

    def generate_content(self):
        for attempt in range(self.config.max_retries):
            try:
                response = self.model.generate_content(self.generate_prompt())
                return self._clean_text(response.text)
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    raise Exception(f"Error after {self.config.max_retries} attempts: {str(e)}")
                print(f"Attempt {attempt + 1} failed, trying again...")
                time.sleep(2)

    def _clean_text(self, text):
        return text.replace("*", "").strip()

class AudioGenerator:
    def __init__(self, config):
        self.config = config
        self.tts = TTS(model_name=config.tts_model)
        self.tts.to("cpu")

    def generate_audio(self, text):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"audio_{timestamp}.wav"
        
        print("\nGenerating Audio...")
        with tqdm(total=1, desc="Generating Speech") as pbar:
            self.tts.tts_to_file(
                text=text,
                speaker=self.config.tts_speaker,
                file_path=str(output_file)
            )
            pbar.update(1)
        
        return output_file

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTML_TEMPLATE

@app.post("/generate")
async def generate_audio():
    try:
        config = Config()
        content_gen = ContentGenerator(config)
        text = content_gen.generate_content()
        
        audio_gen = AudioGenerator(config)
        output_file = audio_gen.generate_audio(text)
        
        # Relativen Pfad für den Download zurückgeben
        relative_path = f"/output/{output_file.name}"
        return {"text": text, "file_path": relative_path}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
