import os
import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── CONFIG ────────────────────────────────────────────
TELEGRAM_TOKEN = "8962146145:AAGn5dfHOetyR86t9VKBX7KECeJXo2rDe-8"
SUPABASE_URL = "https://jzaeywnwjnbrjddyqlvt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp6YWV5d253am5icmpkZHlxbHZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk0NTk3NzgsImV4cCI6MjA5NTAzNTc3OH0.aeNdHkSp_C0I-WrpvInRCHCaGYsNJcqLHOqOWKvu4sQ"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CATEGORIAS = [
    "IA / Automação", "Produto", "Design Gráfico", "Ux/Ui",
    "Ideias Video", "Edição", "Adobe Photoshop", "Adobe After Effects",
    "Adobe Premiere", "Adobe Illustrator", "Prompts Imagens", "Prompts Vídeo"
]

# Prefixos por categoria para gerar títulos consistentes
PREFIXOS = {
    "Ideias Video":         "Referência —",
    "Adobe After Effects":  "AE —",
    "Adobe Premiere":       "PR —",
    "Adobe Photoshop":      "PH —",
    "Adobe Illustrator":    "AI —",
    "Prompts Vídeo":        "Prompt Vídeo —",
    "Prompts Imagens":      "Prompt Imagem —",
    "IA / Automação":       "IA —",
    "Design Gráfico":       "Design —",
    "Ux/Ui":                "UI —",
    "Edição":               "Edição —",
    "Produto":              "Referência —",
}

# Tipo padrão por categoria
TIPOS = {
    "Ideias Video":         "🎥 Vídeo",
    "Adobe After Effects":  "🎥 Vídeo",
    "Adobe Premiere":       "🎥 Vídeo",
    "Adobe Photoshop":      "🎥 Vídeo",
    "Adobe Illustrator":    "🎥 Vídeo",
    "Prompts Vídeo":        "🔗 Link",
    "Prompts Imagens":      "🔗 Link",
    "IA / Automação":       "🛠️ Ferramenta",
    "Design Gráfico":       "🔗 Link",
    "Ux/Ui":                "🔗 Link",
    "Edição":               "🎥 Vídeo",
    "Produto":              "🔗 Link",
}

# Estado por usuário
estado = {}

# ── TÍTULO AUTOMÁTICO ─────────────────────────────────
def gerar_titulo(descricao, categoria):
    prefixo = PREFIXOS.get(categoria, "Referência —")
    desc = descricao.strip().rstrip(".")
    desc = desc[0].upper() + desc[1:] if desc else desc
    return f"{prefixo} {desc}"

# ── TELEGRAM HELPERS ──────────────────────────────────
def send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def answer_callback(callback_id, text=""):
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={
        "callback_query_id": callback_id, "text": text
    })

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}/editMessageText", json=payload)

def categoria_buttons():
    buttons = []
    for i in range(0, len(CATEGORIAS), 2):
        row = [{"text": CATEGORIAS[i], "callback_data": f"cat:{CATEGORIAS[i]}"}]
        if i + 1 < len(CATEGORIAS):
            row.append({"text": CATEGORIAS[i+1], "callback_data": f"cat:{CATEGORIAS[i+1]}"})
        buttons.append(row)
    return {"inline_keyboard": buttons}

def confirmar_buttons():
    return {"inline_keyboard": [
        [
            {"text": "✅ Confirmar", "callback_data": "confirmar"},
            {"text": "✏️ Editar título", "callback_data": "editar_titulo"}
        ],
        [{"text": "❌ Cancelar", "callback_data": "cancelar"}]
    ]}

# ── SUPABASE ──────────────────────────────────────────
def salvar_referencia(titulo, url, categoria, descricao):
    tipo = TIPOS.get(categoria, "🔗 Link")
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/referencias",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        },
        json={
            "titulo": titulo,
            "url": url,
            "categoria": categoria,
            "descricao": descricao,
            "tipo": tipo,
            "tags": []
        }
    )
    return res.status_code in (200, 201)

# ── LÓGICA DO BOT ─────────────────────────────────────
def processar_mensagem(msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if text.startswith("/start"):
        estado.pop(chat_id, None)
        send(chat_id, "👋 Olá! Me manda um link e eu salvo no Banco de Referências.")
        return

    if text.startswith("/cancelar"):
        estado.pop(chat_id, None)
        send(chat_id, "❌ Cancelado. Me manda um novo link quando quiser.")
        return

    s = estado.get(chat_id, {})

    # Aguardando novo título (após "editar título")
    if s.get("step") == "aguardando_novo_titulo":
        estado[chat_id]["titulo"] = text
        estado[chat_id]["step"] = "aguardando_confirmacao"
        titulo = text
        categoria = s.get("categoria")
        descricao = s.get("descricao", "")
        send(chat_id,
             f"📋 <b>Resumo:</b>\n\n"
             f"📌 <b>{titulo}</b>\n"
             f"📂 {categoria}\n"
             f"{'📝 ' + descricao if descricao else ''}\n\n"
             f"Confirmar?",
             reply_markup=confirmar_buttons())
        return

    # Aguardando descrição
    if s.get("step") == "aguardando_descricao":
        descricao = text if text.lower() != "pular" else ""
        categoria = s.get("categoria")

        # Gerar título automaticamente
        if descricao:
            titulo = gerar_titulo(descricao, categoria)
        else:
            titulo = f"{PREFIXOS.get(categoria, 'Referência —')} Sem título"

        estado[chat_id]["descricao"] = descricao
        estado[chat_id]["titulo"] = titulo
        estado[chat_id]["step"] = "aguardando_confirmacao"

        send(chat_id,
             f"📋 <b>Resumo:</b>\n\n"
             f"📌 <b>{titulo}</b>\n"
             f"📂 {categoria}\n"
             f"{'📝 ' + descricao if descricao else ''}\n\n"
             f"Confirmar?",
             reply_markup=confirmar_buttons())
        return

    # Link recebido
    if text.startswith("http://") or text.startswith("https://"):
        estado[chat_id] = {"step": "aguardando_categoria", "url": text, "titulo": None, "categoria": None}
        send(chat_id, f"🔗 Link recebido!\n\nEscolha a categoria:", reply_markup=categoria_buttons())
        return

    # Sem contexto
    send(chat_id, "Me manda um link para começar.\nEx: https://www.instagram.com/reel/...")

def processar_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    callback_id = cb["id"]

    answer_callback(callback_id)
    s = estado.get(chat_id, {})

    # Cancelar
    if data == "cancelar":
        estado.pop(chat_id, None)
        edit_message(chat_id, message_id, "❌ Cancelado. Me manda um novo link quando quiser.")
        return

    # Editar título
    if data == "editar_titulo":
        estado[chat_id]["step"] = "aguardando_novo_titulo"
        edit_message(chat_id, message_id,
                     f"✏️ Me manda o novo título para essa referência:")
        return

    # Confirmar e salvar
    if data == "confirmar":
        titulo = s.get("titulo")
        url = s.get("url")
        categoria = s.get("categoria")
        descricao = s.get("descricao", "")

        ok = salvar_referencia(titulo, url, categoria, descricao)
        estado.pop(chat_id, None)

        if ok:
            edit_message(chat_id, message_id,
                         f"✅ <b>Salvo com sucesso!</b>\n\n"
                         f"📌 <b>{titulo}</b>\n"
                         f"📂 {categoria}\n"
                         f"{'📝 ' + descricao if descricao else ''}\n\n"
                         f"Me manda outro link quando quiser.")
        else:
            edit_message(chat_id, message_id, "❌ Erro ao salvar. Tente novamente.")
        return

    # Selecionar categoria
    if data.startswith("cat:"):
        categoria = data[4:]

        if s.get("step") != "aguardando_categoria":
            edit_message(chat_id, message_id, "⚠️ Sessão expirada. Manda o link de novo.")
            return

        estado[chat_id]["categoria"] = categoria
        estado[chat_id]["step"] = "aguardando_descricao"

        edit_message(chat_id, message_id,
                     f"✅ Categoria: <b>{categoria}</b>\n\n"
                     f"📝 Me manda uma descrição curta do conteúdo\nou manda <b>pular</b> para deixar em branco.")

# ── WEBHOOK SERVER ────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()
        try:
            update = json.loads(body)
            if "message" in update:
                processar_mensagem(update["message"])
            elif "callback_query" in update:
                processar_callback(update["callback_query"])
        except Exception as e:
            print(f"Erro: {e}")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Banco de Referencias Bot - OK")

    def log_message(self, *args):
        pass

PORT = int(os.environ.get("PORT", 8080))
print(f"Bot rodando na porta {PORT}...")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
