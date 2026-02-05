import os
import json
import requests
import re
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

# Configuração
PRICE_HISTORY_FILE = 'price_history.json'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
EVENT_LINK = "https://buyticketbrasil.com/evento/my-chemical-romancedhzo?data=1770426000000&evento_local=1750799113580x614274902513418200"

# Categorias de interesse (Pista Premium apenas)
TARGET_CATEGORIES = ["Meia Estudante", "Inteira", "Acompanhante PCD"]

def load_price_history() -> dict:
    try:
        if os.path.exists(PRICE_HISTORY_FILE):
            with open(PRICE_HISTORY_FILE, 'r') as f:
                history = json.load(f)
                if isinstance(history, dict):
                    # Garante que temos a chave para o menor preço global
                    if "lowest_price" not in history:
                        history["lowest_price"] = 1000000
                    return history
    except:
        pass
    return {"lowest_price": 1000000}

def save_price_history(data):
    with open(PRICE_HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram_alert(price, ticket_type, title="🚨 **NOVO MENOR PREÇO!** 🚨"):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenciais do Telegram não configuradas. Pulando alerta.")
        return

    message = (
        f"{title}\n\n"
        f"Categoria: {ticket_type}\n"
        f"Valor: **R$ {int(price)}**\n\n"
        f"🎫 [Acesse o Site]({EVENT_LINK})"
    )
    
    _send_telegram_msg(message)

def _send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Alerta de menor preço enviado.", flush=True)
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}", flush=True)

def scrape_prices():
    """Navega, interage com Pista Premium e extrai os preços da bubble da Categoria."""
    print("🚀 Iniciando Playwright...", flush=True)
    
    found_tickets = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        try:
            print(f"🔗 Abrindo link...", flush=True)
            page.goto(EVENT_LINK, wait_until="domcontentloaded", timeout=60000)
            
            # Passo 1: Pista Premium
            page.wait_for_selector("text=Tipo de ingresso", timeout=30000)
            page.get_by_text("Tipo de ingresso").first.click()
            page.wait_for_timeout(500)
            page.get_by_text("Pista Premium").first.click()
            page.wait_for_timeout(1000)

            # Passo 2: Abre Categoria (preços aparecem aqui)
            print("☝️ Abrindo categorias para ler preços da bubble...", flush=True)
            cat_btn = page.get_by_text("Categoria").first
            cat_btn.wait_for(state="visible", timeout=5000)
            cat_btn.click()
            page.wait_for_timeout(2000)
            
            # Extração via JS direto nos itens da bubble
            tickets_data = page.evaluate("""() => {
                const results = [];
                const items = Array.from(document.querySelectorAll('.bubble-element.group-item'));
                
                return items.map(item => {
                    const nameEl = item.querySelector('.baUaYjj0');
                    const priceEl = item.querySelector('.baUaYjl0');
                    const qtyEl = item.querySelector('.baUaYjr0');
                    
                    return {
                        name: nameEl ? nameEl.innerText.trim() : "",
                        price: priceEl ? priceEl.innerText.trim() : "",
                        qty: qtyEl ? qtyEl.innerText.trim() : "",
                        raw: item.innerText.trim()
                    };
                });
            }""")
            
            for item in tickets_data:
                name = item['name']
                price_str = item['price']
                
                # Parsing via regex se as classes falharem
                if not name or not price_str:
                    raw = item['raw']
                    match = re.search(r'^(.*?)R\$\s?(\d+)', raw)
                    if match:
                        name = match.group(1).strip()
                        price_str = match.group(2).strip()

                if name and price_str:
                    val_str = re.sub(r'[^\d]', '', price_str)
                    if val_str:
                        price_val = float(val_str)
                        
                        # Filtra apenas categorias desejadas
                        matched_cat = None
                        for target in TARGET_CATEGORIES:
                            if target.lower() in name.lower():
                                matched_cat = target
                                break
                        
                        if matched_cat and price_val > 0:
                            found_tickets.append({
                                "type": matched_cat,
                                "price": price_val
                            })
                            print(f"    -> {matched_cat}: R$ {int(price_val)}", flush=True)

        except Exception as e:
            print(f"🛑 Erro: {e}", flush=True)
        finally:
            browser.close()
            
    return found_tickets

def check_prices():
    """Identifica o mais barato de todos e alerta se baixou."""
    tickets = scrape_prices()
    
    if not tickets:
        print("⚠️ Nenhum ingresso encontrado.", flush=True)
        return

    history = load_price_history()
    last_global_low = float(history.get("lowest_price", 1000000))
    
    # Encontra o ticket MAIS barato entre todos os encontrados
    tickets.sort(key=lambda x: x['price'])
    best_overall = tickets[0]
    current_low = best_overall['price']
    
    print(f"\n📊 Resultado do mais barato: {best_overall['type']} - R$ {int(current_low)}", flush=True)
    print(f"📊 Histórico global para Pista Premium: R$ {int(last_global_low)}", flush=True)

    if current_low < last_global_low:
        print("🔥 NOVO MENOR PREÇO DETECTADO!", flush=True)
        send_telegram_alert(current_low, f"Pista Premium ({best_overall['type']})")
        
        # Atualiza o histórico
        history["lowest_price"] = current_low
        history["last_type"] = best_overall['type']
        save_price_history(history)
    elif current_low > last_global_low:
        print("💸 PREÇO SUBIU - INGRESSO ANTIGO VENDIDO!", flush=True)
        send_telegram_alert(
            current_low, 
            f"Pista Premium ({best_overall['type']})",
            title="⚠️ **INGRESSO ANTERIOR VENDIDO!** ⚠️ \n 💸 NOVO PREÇO MAIS BAIXO:"
        )
        
        # Atualiza o histórico
        history["lowest_price"] = current_low
        history["last_type"] = best_overall['type']
        save_price_history(history)
    else:
        print("✨ O menor preço não baixou.", flush=True)

if __name__ == "__main__":
    check_prices()
