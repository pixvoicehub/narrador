# app.py - VERSÃO FINAL COM CORREÇÃO DO ATRIBUTO 'content'
import os
import base64
import mimetypes
import struct
import io
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pydub import AudioSegment

# --- Configuração Inicial ---
load_dotenv()
app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("ERRO CRÍTICO: A chave da API do Gemini (GEMINI_API_KEY) não está definida.")

# --- Funções de Suporte ---

def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters.get("bits_per_sample", 16)
    sample_rate = parameters.get("rate", 24000)
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE", b"fmt ", 16, 1, num_channels,
        sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", data_size
    )
    return header + audio_data

def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    rate = 24000
    bits_per_sample = 16
    if mime_type:
        parts = mime_type.split(";")
        for param in parts:
            param = param.strip()
            if param.lower().startswith("rate="):
                try:
                    rate = int(param.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}

# --- Rota Principal da API ---

@app.route('/generate-narration', methods=['POST'])
def generate_narration():
    data = request.get_json()
    text_to_speak = data.get('text')
    voice_id = data.get('voiceId')

    if not text_to_speak or not voice_id:
        return jsonify({"error": "Texto e ID do locutor são obrigatórios."}), 400

    try:
        client = genai.Client(api_key=API_KEY)
        model = "gemini-2.5-pro-preview-tts"
        
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=text_to_speak)])]
        
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
                )
            ),
        )

        full_audio_data = bytearray()
        audio_mime_type = "audio/L16;rate=24000"

        for chunk in client.models.generate_content_stream(
            model=model, contents=contents, config=generate_content_config
        ):
            # A CORREÇÃO ESTÁ NA LINHA ABAIXO
            if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                part = chunk.candidates[0].content.parts[0] # Acessando o primeiro candidato e a primeira parte
                if part.inline_data and part.inline_data.data:
                    full_audio_data.extend(part.inline_data.data)
                    if part.inline_data.mime_type:
                        audio_mime_type = part.inline_data.mime_type

        if not full_audio_data:
            return jsonify({"error": "A API não retornou dados de áudio."}), 500

        wav_data = convert_to_wav(bytes(full_audio_data), audio_mime_type)
        
        wav_file_in_memory = io.BytesIO(wav_data)
        audio = AudioSegment.from_file(wav_file_in_memory, format="wav")

        mp3_file_in_memory = io.BytesIO()
        audio.export(mp3_file_in_memory, format="mp3")
        mp3_data = mp3_file_in_memory.getvalue()
        
        audio_base64 = base64.b64encode(mp3_data).decode('utf-8')

        return jsonify({"audioContent": audio_base64})

    except Exception as e:
        print(f"ERRO ao gerar narração com o SDK: {e}")
        return jsonify({"error": f"Ocorreu um erro no servidor ao gerar a narração. Detalhe: {e}"}), 500

# --- Bloco de Execução Local ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
