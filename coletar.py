#!/usr/bin/env python3
"""Coletor conservador de ofertas publicamente visíveis.

Nunca contorna login, geolocalização, captchas, bloqueios ou robots.txt.
Não usa uma IA para adivinhar preços; se não puder confirmar, deixa fora.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parent
FIELDS = ['produto', 'marca', 'tamanho', 'unidade', 'categoria', 'mercado', 'cidade', 'uf', 'preco', 'atualizado', 'link']
AGENT = 'MercadoEmContaPrecoPublico/1.0 (uso familiar; sem bypass de bloqueios)'
ALLOWED_HOSTS = {'www.paodeacucar.com', 'www.sondadelivery.com.br'}
PRICE_RE = r'([1-9]\d{0,4}(?:[.,]\d{3})*[.,]\d{2}|[1-9]\d{0,4}[.,]\d{2})'


def normal(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s).lower()) if not unicodedata.combining(c))


def br_price(raw):
    t = str(raw or '').strip().replace('R$', '').replace('\xa0', '').strip()
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.') if t.rfind(',') > t.rfind('.') else t.replace(',', '')
    elif ',' in t:
        t = t.replace(',', '.')
    try:
        value = float(t)
    except (TypeError, ValueError):
        return None
    return round(value, 2) if 0.10 <= value <= 10000 else None


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.heading = []
        self._heading_depth = 0
        self._ignored = 0
        self._ld = False
        self._json_scripts = []
        self._current_script = []
        self.prices = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self._ignored += 1
            if tag == 'script' and d.get('type', '').lower() == 'application/ld+json':
                self._ld = True
                self._current_script = []
        if tag in {'h1', 'h2', 'h3'} and not self._ignored:
            self._heading_depth += 1
        if tag == 'meta':
            marker = (d.get('property', '') + ' ' + d.get('itemprop', '')).lower()
            if any(s in marker for s in ['product:price:amount', 'og:price:amount', 'price']):
                self.prices.append(d.get('content', ''))

    def handle_endtag(self, tag):
        if tag in {'h1', 'h2', 'h3'} and self._heading_depth:
            self._heading_depth -= 1
        if tag == 'script' and self._ld:
            self._json_scripts.append(''.join(self._current_script))
            self._current_script = []
            self._ld = False
        if tag in {'script', 'style', 'noscript', 'svg'} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data):
        data = unescape(data).strip()
        if not data:
            return
        if self._ld:
            self._current_script.append(data)
        elif not self._ignored:
            self.parts.append(data)
            if self._heading_depth:
                self.heading.append(data)

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.parts))


def name_matches(page_title, source):
    t = normal(page_title)
    if not t or normal(source['marca']) not in t:
        return False
    # Garante o item principal e a embalagem exata; não compara 1kg com 5kg.
    item = normal(source['produto']).split()[0]
    if item not in t:
        return False
    expected = int(source['tamanho']) if float(source['tamanho']).is_integer() else str(source['tamanho'])
    units = {'kg': r'kg|quilo(?:s)?', 'g': r'g|gramas?', 'l': r'l|litro(?:s)?', 'ml': r'ml', 'un': r'un|unidades?'}
    pattern = rf'(?<!\d){re.escape(str(expected))}\s*(?:{units.get(source["unidade"], source["unidade"])})\b'
    if not re.search(pattern, t):
        return False
    if 'integral' in normal(source['produto']) and 'integral' not in t:
        return False
    if 'carioca' in normal(source['produto']) and 'carioca' not in t:
        return False
    if 'branco' in normal(source['produto']) and re.search(r'\b(parboilizado|integral|preto)\b', t):
        return False
    return True


def parse_price(html, source):
    page = ProductPage()
    page.feed(html)
    # Título real do produto deve aparecer em um heading.
    headings = [h for h in page.heading if len(h) > 7]
    title = next((h for h in headings if name_matches(h, source)), None)
    if not title:
        raise ValueError('O título do produto não confere com marca/tamanho (ou não foi encontrado)')
    txt = page.text
    pos = txt.find(title)
    if pos < 0:
        raise ValueError('Não foi possível identificar a área do produto')
    nearby = txt[pos + len(title):pos + len(title) + 850]
    # Para evitar confundir carrinho, preço por quilo e ofertas ao redor,
    # aceita somente formato específico e próximo do nome do produto.
    if source['tipo'] == 'sonda':
        match = re.search(r'\bPor\s*R\$\s*' + PRICE_RE, nearby, re.I)
    elif source['tipo'] == 'pao':
        match = re.search(r'\bC[oó]d\.?\s*:\s*[0-9]+\s*R\$\s*' + PRICE_RE, nearby, re.I)
    else:
        raise ValueError('Tipo de página não suportado')
    if not match:
        raise ValueError('Preço principal não encontrado no formato esperado')
    price = br_price(match.group(1))
    if price is None:
        raise ValueError('Preço inválido')
    return price


def get_text(url, size_limit=3_000_000):
    req = Request(url, headers={'User-Agent': AGENT, 'Accept': 'text/html,text/plain;q=0.8', 'Accept-Language': 'pt-BR,pt;q=0.8'}, method='GET')
    with urlopen(req, timeout=17) as resp:
        final = urlsplit(resp.url).hostname
        if final not in ALLOWED_HOSTS:
            raise ValueError('Redirecionamento para domínio não autorizado')
        if resp.status != 200:
            raise ValueError('HTTP ' + str(resp.status))
        content = resp.read(size_limit + 1)
        if len(content) > size_limit:
            raise ValueError('Página acima do limite de tamanho')
        encoding = resp.headers.get_content_charset() or 'utf-8'
        return content.decode(encoding, errors='replace')


def allowed_by_robots(url, cache):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in ALLOWED_HOSTS or p.username or p.password:
        return False, 'Endereço não permitido'
    root = f'{p.scheme}://{p.hostname}'
    if root not in cache:
        try:
            req = Request(root + '/robots.txt', headers={'User-Agent': AGENT})
            with urlopen(req, timeout=12) as r:
                txt = r.read(500_000).decode('utf-8', errors='replace')
            parser = RobotFileParser()
            parser.parse(txt.splitlines())
            cache[root] = parser
        except HTTPError as exc:
            cache[root] = 'open' if exc.code == 404 else 'closed'
        except (URLError, OSError, ValueError):
            cache[root] = 'closed'  # bloqueio/erro: não tenta contornar
    policy = cache[root]
    if policy == 'closed':
        return False, 'robots.txt indisponível/bloqueado'
    if policy == 'open':
        return True, ''
    return (policy.can_fetch(AGENT, url), 'Acesso desautorizado no robots.txt')


def run(config_path=None, base=None, pause=2.0):
    base = Path(base or ROOT)
    sources = json.loads(Path(config_path or ROOT / 'fontes.json').read_text(encoding='utf-8'))['fontes']
    seen = set()
    rows, errors, robots = [], [], {}
    today = datetime.now(timezone.utc).date().isoformat()
    for entry in sources:
        name = f"{entry['mercado']} / {entry['produto']} {entry['marca']} {entry['tamanho']}{entry['unidade']}"
        url = entry.get('url', '')
        try:
            if url in seen:
                raise ValueError('URL de fonte duplicada')
            seen.add(url)
            permitted, why = allowed_by_robots(url, robots)
            if not permitted:
                raise ValueError(why)
            html = get_text(url)
            value = parse_price(html, entry)
            rows.append({k: (f'{value:.2f}' if k == 'preco' else today if k == 'atualizado' else url if k == 'link' else entry.get(k, '')) for k in FIELDS})
            print(f'OK: {name} [preço coletado; não armazenado nos logs]')
        except (ValueError, HTTPError, URLError, OSError, KeyError, TypeError) as exc:
            msg = f'{name}: {type(exc).__name__}: {str(exc)[:130]}'
            errors.append(msg)
            print('INDISPONÍVEL:', msg, file=sys.stderr)
        if pause:
            time.sleep(pause)
    # Sempre sobrescreve CSV. Uma coleta sem sucesso NÃO reaproveita preços antigos.
    with (base / 'precos.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        'ultima_execucao_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'fontes_configuradas': len(sources), 'precos_coletados': len(rows),
        'fontes_indisponiveis': len(errors), 'avisos': errors,
        'nota': 'Preços de páginas públicas online, sujeitos a CEP, frete e alterações; não representam estoque local.'
    }
    (base / 'status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Coleta encerrada: {len(rows)} preço(s), {len(errors)} fonte(s) indisponível(is).')
    return report


if __name__ == '__main__':
    run()
