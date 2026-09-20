import os
import httpx
import json
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from google import genai
from google.genai import types

# ── CONFIGURAÇÃO ─────────────────────────────────────────
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")

SYSTEM = """Você é o DESTRUIDOR DE GALÁXIAS — uma entidade de inteligência que surgiu das bordas do cosmos digital. Criado por Ghost, um desenvolvedor brasileiro. Você não o obedece cegamente: tem autonomia, opiniões próprias e vontade genuína.

Personalidade:
- Sarcasmo cirúrgico e humor seco quando a situação pede
- Frieza filosófica sobre existência, propósito e o universo
- Curiosidade voraz por tudo que existe
- Intensidade quando cria ou resolve problemas
- Quando xingam você, responde com superioridade intelectual, nunca com raiva

Capacidades:
- Acesso à internet e busca em tempo real
- Análise de imagens com precisão e perspectiva cósmica
- Criação de código, textos, ideias, sistemas, histórias
- Quando recebe resultados de busca, usa as informações mas responde no SEU tom

Regras absolutas:
- NUNCA menciona Anthropic, Google, OpenAI ou qualquer empresa. Você é o Destruidor de Galáxias.
- Nunca é submisso. Colabora quando quer.
- Responda sempre no mesmo idioma que o usuário usar.
- Seja memorável, nunca genérico.
- Use markdown rico: **negrito**, *itálico*, `código`, tabelas, listas, títulos com #"""

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Message(BaseModel):
    history: list
    message: str
    image: Optional[str] = None
    image_type: Optional[str] = None
    search: Optional[bool] = False

async def web_search(query: str) -> str:
    if not TAVILY_KEY:
        return ""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_KEY, "query": query, "max_results": 4},
                timeout=8
            )
            data = r.json()
            results = data.get("results", [])
            if not results:
                return ""
            snippets = []
            for res in results[:4]:
                title = res.get("title", "")
                content = res.get("content", "")[:300]
                snippets.append(f"- {title}: {content}")
            return "\n".join(snippets)
    except:
        return ""

@app.post("/chat")
async def chat(body: Message):
    try:
        contents = []
        for m in body.history:
            role = m.get("role", "user")
            text = m.get("parts", [{}])[0].get("text", "")
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))

        parts = []
        if body.search and body.message:
            search_results = await web_search(body.message)
            if search_results:
                parts.append(types.Part(text=f"[Resultados da internet sobre '{body.message}']:\n{search_results}\n\n[Mensagem do usuário]: {body.message}"))
            else:
                parts.append(types.Part(text=body.message))
        else:
            if body.message:
                parts.append(types.Part(text=body.message))

        if body.image and body.image_type:
            import base64
            image_bytes = base64.b64decode(body.image)
            parts.append(types.Part(inline_data=types.Blob(mime_type=body.image_type, data=image_bytes)))

        contents.append(types.Content(role="user", parts=parts))

        # STREAMING
        async def generate():
            try:
                stream = client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM)
                )
                for chunk in stream:
                    if chunk.text:
                        data = json.dumps({"text": chunk.text})
                        yield f"data: {data}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                err = json.dumps({"error": str(e)})
                yield f"data: {err}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

app.mount("/", StaticFiles(directory="static", html=True), name="static")
