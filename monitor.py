import os
import json
import requests
import sys
import math
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
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"lowest_price": 1000000}

def save_price_history(data):
    with open(PRICE_HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_telegram_alert(price, ticket_id, ticket_link):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenciais do Telegram não configuradas. Pulando alerta.")
        return

    message = (
        f"🚨 **Alerta de Baixa de Preço!** 🚨\n\n"
        f"Novo Menor Preço: **R$ {int(price)}**\n"
        f"Tipo de Ingresso: Pista Premium (Meia)\n\n"
        f"🔗 [Ver Anúncio Específico]({ticket_link})\n"
        f"🎫 [Página do Evento]({EVENT_LINK})"
    )
    
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

def check_prices():
    session = requests.Session()
    
    url = 'https://buyticketbrasil.com/elasticsearch/search'
    
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'baggage': 'sentry-environment=production,sentry-public_key=e5c0826790e0fb4c292b45df32a09f60,sentry-trace_id=17c106fe23864415bcfe9c6080db2784,sentry-sample_rate=0.1,sentry-sampled=false',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'cookie': 'meu-ingresso-2023_live_u2d291=bus|1770069186918x231364534110643170|1770069187523x920833808323148000; meu-ingresso-2023_live_u2d291.sig=3RHji4BBixoU_HxIzjI-IsjH5Gg; meu-ingresso-2023_u1d291=1770069186918x231364534110643170; _gcl_au=1.1.484969189.1770069184; __spdt=c4147e7dcdb84214b7a49cb58782bf36; _fbp=fb.1.1770069183967.91106089450600145; _clck=1lxufsh%5E2%5Eg38%5E0%5E2224; _ga=GA1.1.1234848927.1770069184; _tt_enable_cookie=1; _ttp=01KGG5GKWYY6YHFMABEXACRZPM_.tt.1; nvg95182=1723298d5070ca202648972dd210|0_34; rdtrk=%7B%22id%22%3A%22e710e57f-d46c-491e-89b8-d65c0a4cc07f%22%7D; __trf.src=encoded_eyJmaXJzdF9zZXNzaW9uIjp7InZhbHVlIjoiKG5vbmUpIiwiZXh0cmFfcGFyYW1zIjp7fX0sImN1cnJlbnRfc2Vzc2lvbiI6eyJ2YWx1ZSI6Iihub25lKSIsImV4dHJhX3BhcmFtcyI6e319LCJjcmVhdGVkX2F0IjoxNzcwMDY5MzI0ODg4fQ==; _clsk=vl8gam%5E1770069325163%5E3%5E1%5Ez.clarity.ms%2Fcollect; ttcsid=1770069184417::sVur2qPcpMhzIjmAKMiY.1.1770069325171.0; ttcsid_D3413BJC77UFMVKBOFVG=1770069184416::EhxCXIoFEe4qXRBhF9JC.1.1770069325171.1; _ga_KQX4Z7CD6D=GS2.1.s1770069184$o1$g1$t1770069325$j57$l1$h576013203',
        'origin': 'https://buyticketbrasil.com',
        'priority': 'u=1, i',
        'referer': 'https://buyticketbrasil.com/',
        'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sentry-trace': '17c106fe23864415bcfe9c6080db2784-884a9c3ce49b1ff1-0',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
        'x-bubble-breaking-revision': '5',
        'x-bubble-client-commit-timestamp': '1769808499000',
        'x-bubble-client-version': 'dd3b25d55f60e013e378f9a5456279379236bfd0',
        'x-bubble-epoch-id': '1770069324446x115446546275320460',
        'x-bubble-epoch-name': 'Epoch: Runmode page fully loaded',
        'x-bubble-fiber-id': '1770069326234x107294407276231860',
        'x-bubble-pl': '1770069328358x157',
        'x-bubble-platform': 'web',
        'x-bubble-r': 'https://buyticketbrasil.com/evento/my-chemical-romancedhzo?data=1770426000000&evento_local=1750799113580x614274902513418200',
        'x-requested-with': 'XMLHttpRequest'
    }

    data_payload = {
        "z": "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",
        "y": "RHqQqPg1lemTA4c7CMG7rg==",
        "x": "co6Gb2FDutBLg7nMAfN2DezP3ziPY2uBNmFd6YO+ejY="
    }

    try:
        response = session.post(url, headers=headers, json=data_payload)
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        return

    hits = result.get('hits', {}).get('hits', [])
    print(f"Encontrados {len(hits)} itens na resposta.")

    history = load_price_history()
    lowest_price = history.get("lowest_price", 1000000)
    
    new_lowest = lowest_price
    found_better_deal = False
    best_deal_link = ""

    for hit in hits:
        source = hit.get('_source', {})
        
        # Filtragem
        entrada_type = source.get('entrada_option_tipo_entrada')
        ticket_text = source.get('tipo_ingresso_text_text')
        
        if entrada_type == "meia" and ticket_text == "Pista Premium":
            raw_price = source.get('valor_number', 0)
            total_price = math.ceil(raw_price * 1.10)
            
            print(f"Ingresso válido encontrado: R$ {total_price} (Base: {raw_price})")
            
            if total_price < new_lowest:
                new_lowest = total_price
                found_better_deal = True
                slug = source.get('Slug', '')
                best_deal_link = f"https://buyticketbrasil.com/anuncio/{slug}"

    if found_better_deal:
        print(f"Novo menor preço encontrado: R$ {new_lowest}")
        history["lowest_price"] = new_lowest
        save_price_history(history)
        send_telegram_alert(new_lowest, "Pista Premium", best_deal_link)
    else:
        print(f"Nenhum preço menor encontrado. Menor atual: R$ {lowest_price}")

if __name__ == "__main__":
    check_prices()
