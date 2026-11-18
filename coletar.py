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
    """Lê somente texto visível, títulos completos e dados estruturados.

    Um título pode conter vários <span>s: não se deve validar cada fragmento
    isoladamente. Scripts só são analisados quando são JSON-LD (Schema.org).
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.heading = []  # mantido para compatibilidade
        self.heading_blocks = []
        self._heading_tag = None
        self._heading_parts = []
        self._ignored = 0
        self._json_ld_active = False
        self._json_scripts = []
        self._current_script = []
        self.prices = []
        self.price_currencies = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in {'script', 'style', 'noscript', 'svg'}:
            if tag == 'script' and self._ignored == 0 and d.get('type', '').lower().strip() == 'application/ld+json':
                self._json_ld_active = True
                self._current_script = []
            self._ignored += 1
            return
        if self._ignored:
            return
        if tag in {'h1', 'h2', 'h3'} and self._heading_tag is None:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == 'meta':
            marker = ' '.join(str(d.get(k, '')) for k in ('property', 'itemprop', 'name')).lower()
            if any(x in marker for x in ('product:price:amount', 'og:price:amount')) or marker.strip() == 'price':
                self.prices.append(d.get('content', ''))
            if 'pricecurrency' in marker or 'price:currency' in marker:
                self.price_currencies.append(d.get('content', ''))

    def handle_endtag(self, tag):
        if tag == self._heading_tag and not self._ignored:
            title = re.sub(r'\s+', ' ', ' '.join(self._heading_parts)).strip()
            if title:
                self.heading_blocks.append(title)
                self.heading.append(title)
            self._heading_tag = None
            self._heading_parts = []
        if tag == 'script' and self._json_ld_active:
            self._json_scripts.append(''.join(self._current_script))
            self._json_ld_active = False
            self._current_script = []
        if tag in {'script', 'style', 'noscript', 'svg'} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data):
        if self._json_ld_active:
            self._current_script.append(data)
            return
        if self._ignored:
            return
        data = unescape(data).strip()
        if data:
            self.parts.append(data)
            if self._heading_tag:
                self._heading_parts.append(data)

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.parts))


def jsonld_prices(page, source):
    """Preços de ofertas Schema.org do produto exato, sem chutar valores.

    Só aceita um preço inequívoco e moeda BRL (ou não especificada).
    Ofertas de outros produtos, AggregateOffer e itens esgotados são ignorados.
    """
    candidates = set()
    def visit(node):
        if isinstance(node, list):
            for part in node:
                visit(part)
            return
        if not isinstance(node, dict):
            return
        types = node.get('@type', '')
        types = types if isinstance(types, list) else [types]
        if any(str(t).lower().split('/')[-1] == 'product' for t in types):
            if name_matches(str(node.get('name', '')), source):
                offers = node.get('offers', [])
                offers = offers if isinstance(offers, list) else [offers]
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    typ = offer.get('@type', 'Offer')
                    types2 = typ if isinstance(typ, list) else [typ]
                    if not any(str(t).lower().split('/')[-1] == 'offer' for t in types2):
                        continue
                    if str(offer.get('priceCurrency', 'BRL')).upper() != 'BRL':
                        continue
                    availability = str(offer.get('availability', '')).lower()
                    if any(x in availability for x in ('outofstock', 'soldout', 'discontinued', 'preorder')):
                        continue
                    price = offer.get('price')
                    if price is None and isinstance(offer.get('priceSpecification'), dict):
                        spec = offer['priceSpecification']
                        if str(spec.get('priceCurrency', 'BRL')).upper() == 'BRL':
                            price = spec.get('price')
                    value = br_price(price)
                    if value is not None:
                        candidates.add(value)
        for nested in node.values():
            if isinstance(nested, (dict, list)):
                visit(nested)
    for raw in page._json_scripts:
        try:
            visit(json.loads(raw))
        except (ValueError, TypeError, RecursionError):
            continue
    return candidates

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
    """Lê o preço principal de uma página do produto, com múltiplos formatos.

    Prioridades: oferta JSON-LD verificável; preço exibido imediatamente após
    o título confirmado. Nunca pega total do carrinho, preço por kg, recomendação
    de outro produto ou valores sem identidade.
    """
    page = ProductPage()
    page.feed(html)

    titles = [h for h in page.heading_blocks if name_matches(h, source)]
    if not titles:
        raise ValueError('Produto exato não encontrado no título da página (marca/embalagem)')

    structured = jsonld_prices(page, source)
    if len(structured) == 1:
        return structured.pop()
    if len(structured) > 1:
        raise ValueError('Múltiplos preços conflitantes no JSON-LD')

    # Pega o trecho depois do título de produto (e não a barra de navegação).
    visible = page.text
    title = max(titles, key=len)
    start = visible.find(title)
    if start < 0:
        raise ValueError('Área do produto não localizada no HTML visível')
    nearby = visible[start + len(title):start + len(title) + 900]
    # Não examina recomendações, rodapé ou especificações distantes.
    nearby = re.split(r'\b(?:descri[cç][aã]o do produto|informa[cç][oõ]es nutricionais|produtos relacionados|quem comprou tamb[eé]m|voc[eê] tamb[eé]m pode)\b', nearby, maxsplit=1, flags=re.I)[0]
    # Sem texto visível ainda é possível haver uma meta tag válida.

    # Valores do carrinho e de unidade não são preço total do produto.
    price_amount = r'((?:[1-9]\d{0,2}(?:\.\d{3})+|[1-9]\d{0,4}),\d{2})'
    patterns = [
        r'\bPor\s*R\$\s*' + price_amount,  # Sonda e promoções
        r'\b(?:Pre[cç]o(?:\s+(?:de\s+)?venda)?|Valor)\s*:?\s*R\$\s*' + price_amount,
        r'R\$\s*' + price_amount,              # Pão: Cód. 123 R$ 27,99
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, nearby, re.I):
            prefix = nearby[max(0, match.start()-44):match.start()].lower()
            # Preço por 1kg/1L e totais/resumos não servem à comparação.
            if re.search(r'(?:pre[cç]o\s+por\s*(?:\d+\s*)?(?:kg|g|l|ml|unidade)|subtotal|carrinho|frete|economize|desconto)\s*[-:]?\s*$', prefix, re.I):
                continue
            if re.search(r'\bde\s*$', prefix, re.I):
                continue  # preço antigo "De R$", não a oferta atual
            value = br_price(match.group(1))
            if value is not None:
                return value

    # Meta tags publicadas para este produto: aceita somente preço único.
    currencies = {str(c).upper() for c in page.price_currencies if c}
    if currencies and currencies != {'BRL'}:
        raise ValueError('Meta tag com moeda diferente de BRL')
    meta_values = {v for raw in page.prices if (v := br_price(raw)) is not None}
    if len(meta_values) == 1:
        return meta_values.pop()

    raise ValueError('Preço principal não identificado com segurança (página pode exigir JavaScript/CEP)')

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
