import os
import json
import requests
import sys
import math
import time
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# Configuração
PRICE_HISTORY_FILE = 'price_history.json'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
EVENT_LINK = "https://buyticketbrasil.com/evento/my-chemical-romancedhzo?data=1770426000000&evento_local=1750799113580x614274902513418200"

def load_price_history():
    try:
        with open(PRICE_HISTORY_FILE, 'r') as f:
            history = json.load(f)
            # Ensure safe defaults for new fields
            if "lowest_price" not in history:
                history["lowest_price"] = 1000000
            if "last_cheapest_id" not in history:
                history["last_cheapest_id"] = None
            return history
    except (FileNotFoundError, json.JSONDecodeError):
        return {"lowest_price": 1000000, "last_cheapest_id": None}

def save_price_history(data):
    with open(PRICE_HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram_alert(price, ticket_id,):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenciais do Telegram não configuradas. Pulando alerta.")
        return

    message = (
        f"🚨 **Alerta de Baixa de Preço!** 🚨\n\n"
        f"Novo Menor Preço: **R$ {int(price)}**\n"
        f"Tipo de Ingresso: Pista Premium (Meia)\n\n"
        f"🎫 [Página do Evento]({EVENT_LINK})"
    )
    
    _send_telegram_msg(message)

def send_sold_alert(old_price, new_price):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenciais do Telegram não configuradas. Pulando alerta.")
        return

    message = (
        f"🎫 **Ingresso Vendido!**\n\n"
        f"O último mais barato (**R$ {int(old_price)}**) foi vendido.\n"
        f"Esse é o ingresso mais barato atualmente: **R$ {int(new_price)}**\n\n"
        f"🎫 [Página do Evento]({EVENT_LINK})"
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
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Alerta do Telegram enviado com sucesso.")
    except Exception as e:
        print(f"Falha ao enviar alerta do Telegram: {e}")

def get_dynamic_data():
    """Captura dados da sessão e tenta encontrar o payload de busca correto."""
    print("Iniciando Playwright para capturar sessão e encontrar a busca de ingressos...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        context = browser.new_context(user_agent=ua)
        page = context.new_page()
        
        # Lista para armazenar candidatos a busca
        candidates = []

        def on_request(request):
            if "elasticsearch/search" in request.url and request.method == "POST":
                headers = request.headers
                referer = headers.get("x-bubble-r", "") or headers.get("referer", "")
                if "my-chemical-romance" in referer.lower():
                    candidates.append({
                        "headers": headers,
                        "payload": request.post_data
                    })

        page.on("request", on_request)
        
        print(f"Navegando para: {EVENT_LINK}")
        try:
            page.goto(EVENT_LINK, wait_until="domcontentloaded", timeout=480000)
            
            # Rola a página devagar para disparar tudo
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(1000)
            
            # Espera um tempo razoável para todos os disparos
            print("Aguardando disparos de busca (10s)...")
            page.wait_for_timeout(10000)
                
            if not candidates:
                print("DEBUG: Nenhuma busca detectada.")
                return None

            print(f"Detectadas {len(candidates)} requisições de busca. Testando candidatos...")
            
            best_result = None
            max_anuncios = -1
            
            for i, cand in enumerate(candidates):
                print(f"Testando candidato {i+1}/{len(candidates)}...")
                try:
                    api_url = "https://buyticketbrasil.com/elasticsearch/search"
                    api_response = context.request.post(
                        api_url,
                        headers=cand["headers"],
                        data=cand["payload"],
                        timeout=60000
                    )
                    
                    if api_response.ok:
                        data = api_response.json()
                        hits = data.get('hits', {}).get('hits', [])
                        # Conta quantos são anuncios
                        anuncios = len([h for h in hits if "anuncio" in h.get('_type', '').lower()])
                        total = len(hits)
                        print(f"  -> Total hits: {total}, Anúncios: {anuncios}")
                        
                        # Atribuímos como melhor se tiver mais anúncios ou se for o que tem perto de 343 itens
                        if anuncios > max_anuncios or (anuncios == 0 and total > max_anuncios):
                            max_anuncios = anuncios if anuncios > 0 else total
                            best_result = data
                except Exception as e:
                    print(f"  -> Erro ao testar candidato: {e}")

            if best_result:
                return best_result
            else:
                print("DEBUG: Nenhum candidato retornou dados válidos.")
                return None

        except Exception as e:
            print(f"Erro no Playwright: {e}")
            return None
        finally:
            browser.close()

def check_prices():
    """Busca preços usando os resultados capturados via Playwright."""
    result = get_dynamic_data()
    
    if not result:
        print("Erro: Não foi possível obter os dados da busca.")
        return

    # Salva a resposta bruta para inspeção manual
    with open('response.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    print("Resposta completa salva em response.json")

    hits = result.get('hits', {}).get('hits', [])
    total_data = result.get('hits', {}).get('total', 0)
    
    if isinstance(total_data, dict):
        total_hits = total_data.get('value', 0)
    else:
        total_hits = total_data
    
    print(f"Total de hits no Elasticsearch: {total_hits}")
    print(f"Itens retornados nesta requisição (len(hits)): {len(hits)}")

    history = load_price_history()
    last_lowest_price = history.get("lowest_price", 1000000)
    last_cheapest_id = history.get("last_cheapest_id")
    
    current_tickets = []

    for hit in hits:
        source = hit.get('_source', {})
        hit_id = hit.get('_id')
        
        # Filtragem
        entrada_type = source.get('entrada_option_tipo_entrada')
        ticket_text = source.get('tipo_ingresso_text_text')
        
        if entrada_type == "meia" and ticket_text == "Pista Premium":
            raw_price = source.get('valor_number', 0)
            total_price = math.ceil(raw_price * 1.10)
            slug = source.get('Slug', '')
            link = f"https://buyticketbrasil.com/anuncio/{slug}"
            
            current_tickets.append({
                "id": hit_id,
                "price": total_price,
                "link": link
            })
            print(f"Ingresso válido encontrado: R$ {total_price} (ID: {hit_id})")

    if not current_tickets:
        print("Nenhum ingresso válido encontrado no momento.")
        return

    # Encontrar o mais barato atual
    current_tickets.sort(key=lambda x: x['price'])
    best_deal = current_tickets[0]
    
    new_lowest = best_deal['price']
    new_cheapest_id = best_deal['id']

    # Lógica 1: Se o que era o mais barato foi vendido
    was_sold = False
    if last_cheapest_id and not any(t['id'] == last_cheapest_id for t in current_tickets):
        print(f"O último ingresso mais barato (ID: {last_cheapest_id}) foi vendido!")
        send_sold_alert(last_lowest_price, new_lowest)
        was_sold = True

    # Lógica 2: Se apareceu um NOVO menor preço (mesmo que o anterior não tenha sido vendido)
    if new_lowest < last_lowest_price:
        print(f"Novo menor preço encontrado: R$ {new_lowest}")
        if not was_sold: # Evita mandar dois alertas se ele era o anterior (embora se for menor, não seria o mesmo ID se estivessemos rastreando certo)
            send_telegram_alert(new_lowest, "Pista Premium")
                
        history["lowest_price"] = new_lowest
        history["last_cheapest_id"] = new_cheapest_id
        save_price_history(history)
    elif was_sold:
        # Se foi vendido mas o preço subiu (ou manteve), ainda precisamos atualizar o history com o novo ID/Preço
        history["lowest_price"] = new_lowest
        history["last_cheapest_id"] = new_cheapest_id
        save_price_history(history)
    else:
        print(f"Nenhum novo menor preço e o anterior ainda está disponível. Menor atual: R$ {last_lowest_price}")

if __name__ == "__main__":
    check_prices()
