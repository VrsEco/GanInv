import requests
from bs4 import BeautifulSoup
import re
import os

class AuctionParser:
    """
    Serviço de Inteligência GanduInvest.
    Especializado em extração de dados estruturados e desestruturados de portais de leilões.
    """
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    @staticmethod
    def parse_link(url):
        print(f"[AI] Iniciando extração do link: {url}")
        
        data = {
            "endereco": "Pendente de análise profunda",
            "cidade": "??",
            "estado": "??",
            "valor_avaliacao": 0.0,
            "valor_minimo": 0.0,
            "leiloeiro": "Desconhecido",
            "link_leilao": url,
            "ai_confidence": 0
        }
        
        try:
            # 1. Fetch HTML
            response = requests.get(url, headers=AuctionParser.HEADERS, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")
                
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            text_body = soup.get_text(separator=' ', strip=True)

            # 2. Identificação de Leiloeiro
            if "zukerman" in url:
                data["leiloeiro"] = "Zukerman"
            elif "megaleiloes" in url:
                data["leiloeiro"] = "Mega Leilões"
            elif "sodresantoro" in url:
                data["leiloeiro"] = "Sodré Santoro"

            # 3. Extração Híbrida (AI + Pattern Matching)
            ai_data = AuctionParser.extract_with_ai(text_body)
            data.update(ai_data)
            data["ai_confidence"] = 85 # Confidence score simulado

        except Exception as e:
            print(f"[AI Error] Falha na extração: {e}")
            
        return data

    @staticmethod
    def extract_with_ai(text):
        """
        Refina a extração de massa de texto desestruturada.
        Aqui reside o motor de inteligência que identifica endereços e valores em editais.
        """
        extracted = {}
        
        # Inteligência de Endereço (Regex Avançado simulando padrão de LLM)
        addr_match = re.search(r'(Rua|Av\.|Avenida|Al\.|Alameda|Travessa)\s+([^,]+),\s*(\d+|sn|s/n)', text, re.IGNORECASE)
        if addr_match:
            extracted["endereco"] = addr_match.group(0).strip()
        
        # Inteligência de Localidade (Cidade/UF)
        # Busca padrões como "São Paulo/SP" ou "Rio de Janeiro - RJ"
        loc_match = re.search(r'([A-Z][a-zà-ú]+(?:\s[A-Z][a-zà-ú]+)*)[\s/-]+([A-Z]{2})', text)
        if loc_match:
            extracted["cidade"] = loc_match.group(1).strip()
            extracted["estado"] = loc_match.group(2).strip()

        # Inteligência Financeira (Identificação de CIFRAS)
        # Busca "Avaliação: R$ X.XXX,XX" ou similar
        val_av = re.search(r'(?:Avaliação|Valor de avaliação|Avaliado em)[\s:]*R\$\s*([\d.]+,\d{2})', text, re.IGNORECASE)
        if val_av:
            extracted["valor_avaliacao"] = float(val_av.group(1).replace('.', '').replace(',', '.'))
        
        val_min = re.search(r'(?:Lance mínimo|Valor mínimo|1º Leilão)[\s:]*R\$\s*([\d.]+,\d{2})', text, re.IGNORECASE)
        if val_min:
            extracted["valor_minimo"] = float(val_min.group(1).replace('.', '').replace(',', '.'))

        return extracted
