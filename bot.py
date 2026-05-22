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

# Estado por usuário: { chat_id: { "step": ..., "url": ..., "categoria": ... } }
estado = {}

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

def edit_message(chat_id, message_id, text):
    requests.post(f"{TELEGRAM_API}/editMessageText", json={
        "chat_id": chat_id, "message_id": message_id,
        "text": text, "parse_mode": "HTML"
    })

def categoria_buttons():
    """Monta teclado inline 2 colunas com as categorias."""
    buttons = []
    for i in range(0, len(CATEGORIAS), 2):
        row = [{"text": CATEGORIAS[i], "callback_data": f"cat:{CATEGORIAS[i]}"}]
        if i + 1 < len(CATEGORIAS):
            row.append({"text": CATEGORIAS[i+1], "callback_data": f"cat:{CATEGORIAS[i+1]}"})
        buttons.append(row)
    return {"inline_keyboard": buttons}

# ── SUPABASE ──────────────────────────────────────────
def salvar_referencia(titulo, url, categoria, descricao):
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/referencias",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        },
        json={"titulo": titulo, "url": url, "categoria": categoria,
              "descricao": descricao, "tipo": "🎥 Vídeo", "tags": []}
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

    # Aguardando descrição
    if s.get("step") == "aguardando_descricao":
        descricao = text if text.lower() != "pular" else None
        url = s.get("url")
        categoria = s.get("categoria")
        titulo = s.get("titulo") or url

        ok = salvar_referencia(titulo, url, categoria, descricao)
        estado.pop(chat_id, None)

        if ok:
            send(chat_id,
                 f"✅ <b>Salvo!</b>\n\n"
                 f"📌 <b>{titulo}</b>\n"
                 f"📂 {categoria}\n"
                 f"{'📝 ' + descricao if descricao else ''}\n\n"
                 f"Me manda outro link quando quiser.")
        else:
            send(chat_id, "❌ Erro ao salvar no Supabase. Tente novamente.")
        return

    # Aguardando título
    if s.get("step") == "aguardando_titulo":
        estado[chat_id]["titulo"] = text
        estado[chat_id]["step"] = "aguardando_descricao"
        send(chat_id, "📝 Me manda uma descrição rápida ou manda <b>pular</b> para deixar em branco.")
        return

    # Link recebido — detectar URL
    if text.startswith("http://") or text.startswith("https://"):
        estado[chat_id] = {"step": "aguardando_categoria", "url": text, "titulo": None, "categoria": None}
        send(chat_id, f"🔗 Link recebido!\n\n<code>{text}</code>\n\nEscolha a categoria:", reply_markup=categoria_buttons())
        return

    # Sem contexto
    send(chat_id, "Me manda um link para começar. Ex:\nhttps://www.instagram.com/reel/...")

def processar_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    callback_id = cb["id"]

    answer_callback(callback_id)

    if data.startswith("cat:"):
        categoria = data[4:]
        s = estado.get(chat_id, {})

        if s.get("step") != "aguardando_categoria":
            edit_message(chat_id, message_id, "⚠️ Sessão expirada. Manda o link de novo.")
            return

        estado[chat_id]["categoria"] = categoria
        estado[chat_id]["step"] = "aguardando_titulo"

        edit_message(chat_id, message_id,
                     f"✅ Categoria: <b>{categoria}</b>\n\n"
                     f"Agora me manda um título para essa referência.\n"
                     f"(Ex: <i>Referência Match Cut — Adidas</i>)")

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
        pass  # silenciar logs do servidor

PORT = int(os.environ.get("PORT", 8080))
print(f"Bot rodando na porta {PORT}...")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
