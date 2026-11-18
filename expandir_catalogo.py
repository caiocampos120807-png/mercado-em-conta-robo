#!/usr/bin/env python3
"""Descoberta incremental em páginas públicas permitidas + preços verificáveis.

Extensão gratuita ao coletor original. Não usa login, APIs ocultas,
CAPTCHA, proxy, browser automatizado ou dados falsos.
Python 3.12 stdlib; execução via GitHub Actions. Falha fechada para robots.
"""
from __future__ import annotations

import csv
import json
import itertools
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote

import coletar

ROOT = Path(__file__).resolve().parent
FIELDS = coletar.FIELDS
HOSTS = {"www.paodeacucar.com": "Pão de Açúcar (online)",
         "www.sondadelivery.com.br": "Sonda (online)"}
LIST_START = [
    "https://www.paodeacucar.com/sitemapProduto.sdex",
    "https://www.sondadelivery.com.br/delivery/hotsite/superofertas",
    "https://www.sondadelivery.com.br/delivery/categoria/Mercearia",
    "https://www.sondadelivery.com.br/delivery/categoria/Bebidas_nao_Alcoolicas",
    "https://www.sondadelivery.com.br/delivery/categoria/Limpeza",
    "https://www.sondadelivery.com.br/delivery/categoria/Acougue",
    "https://www.sondadelivery.com.br/delivery/categoria/Hortifruti",
    "https://www.sondadelivery.com.br/delivery/categoria/Frios_e_Laticinios",
    "https://www.sondadelivery.com.br/delivery/categoria/Higiene_e_Beleza",
    "https://www.sondadelivery.com.br/delivery/categoria/Padaria",
    "https://www.sondadelivery.com.br/delivery/categoria/Congelados",
    "https://www.sondadelivery.com.br/delivery/categoria/Utilidades_e_Bazar",
]
# Marcas reconhecidas pelo nome publicado na página; sem inventar marcas.
BRANDS = [
    "Camil", "Parmalat", "Qualitá", "Taeq", "Sadia", "Seara", "Friboi", "Perdigão",
    "Nestlé", "Ninho", "Itambé", "Piracanjuba", "Vigor", "Danone", "Batavo",
    "Bauducco", "Panco", "Wickbold", "Pullman", "Nissin", "Adria", "Renata",
    "Barilla", "Galo", "Tio João", "Kicaldo", "Urbano", "Namorado", "Korin",
    "3 Corações", "Três Corações", "Pilão", "Melitta", "Nescafé", "União",
    "Caravelas", "Carrefour", "Yoki", "Kellogg's", "Kelloggs", "Quaker",
    "Hellmann's", "Heinz", "Fugini", "Elefante", "Predilecta", "Pomarola",
    "Coca-Cola", "Pepsi", "Guaraná Antarctica", "Fanta", "Sprite", "Schweppes",
    "Del Valle", "Tang", "Dolly", "Maguary", "Natural One", "Prats", "Minalba",
    "Crystal", "Bonafont", "Indaiá", "Bona", "Liza", "Soya", "Sinhá", "Gallo",
    "Andorinha", "Cocinero", "Borges", "Omo", "Brilhante", "Ariel", "Tixan",
    "Ypê", "Minuano", "Veja", "Cif", "Limpol", "Bombril", "Assolan", "Pinho Sol",
    "Downy", "Comfort", "Fofo", "Mon Bijou", "Harpic", "Vanish", "Qboa",
    "Colgate", "Oral-B", "Sensodyne", "Closeup", "Sorriso", "Dove", "Rexona",
    "Nivea", "Nívea", "Seda", "Pantene", "Elseve", "Tresemmé", "Johnson's",
    "Johnson", "Huggies", "Pampers", "Personal", "Neve", "Snob", "Mili",
    "Cotton", "Aviação", "Becel", "Doriana", "Claybom", "President", "Polenghi",
    "Tirolez", "Catupiry", "Philadelphia", "McCain", "Pioneiro", "Swift",
]
UNITS = {"gramas":"g", "grama":"g", "quilo":"kg", "quilos":"kg",
         "litro":"l", "litros":"l", "unidade":"un", "unidades":"un",
         "un":"un", "kg":"kg", "g":"g", "ml":"ml", "l":"l"}
SIZE_RE = re.compile(r"(?<!\w)(\d{1,4}(?:[.,]\d{1,3})?)\s*(kg|ml|g|litros?|l|gramas?|quilos?|unidades?|un)\b", re.I)
BLOCKED = {"cerveja", "vinho", "whisky", "vodka", "gin", "destilado", "espumante", "cigarro", "tabaco", "medicamento"}


def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s).lower()) if not unicodedata.combining(c))


def now():
    return datetime.now(timezone.utc)


def stamp(value=None):
    return (value or now()).isoformat(timespec='seconds')


def parse_when(s):
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def safe_url(href, base=None, kind="product"):
    """Evita buscar URLs fora dos dois domínios, URLs com tokens/credenciais ou pesquisas."""
    if not isinstance(href, str) or len(href) > 1500:
        return None
    u = urlsplit(urljoin(base or '', href))
    if u.scheme != 'https' or u.hostname not in HOSTS or u.username or u.password or u.port:
        return None
    path = u.path
    if not path or '/..' in unquote(path) or '%2f' in path.lower():
        return None
    if kind == 'product':
        if u.hostname == 'www.paodeacucar.com':
            if not re.fullmatch(r'/produto/\d+/[\w%\-]+/?', path, re.I):
                return None
        else:
            if not re.fullmatch(r'/delivery/produto/[\w%\-]+/\d+/?', path, re.I):
                return None
        return urlunsplit(('https', u.hostname, path.rstrip('/'), '', ''))
    if kind == 'listing':
        if u.hostname == 'www.paodeacucar.com':
            if not re.fullmatch(r'/sitemapProduto(?:-\d+)?\.sdex', path, re.I):
                return None
        elif not re.fullmatch(r'/delivery/(?:categoria/(?:[\w%\-]+/){0,5}[\w%\-]+|hotsite/superofertas(?:/\d+)?)/?', path, re.I):
            return None
        # Query de paginação simples é permitida; filtros/cookies não são.
        q = u.query
        if q and not re.fullmatch(r'(?:pagina|page|p)=\d{1,3}', q, re.I):
            return None
        return urlunsplit(('https', u.hostname, path.rstrip('/'), q, ''))
    return None


class LinkParser(HTMLParser):
    """Extrai URLs de href sem varrer JavaScript de terceiros."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


def discover(html, source_url):
    parser = LinkParser()
    parser.feed(html)
    products, pages = set(), set()
    for href in parser.links:
        p = safe_url(href, source_url, 'product')
        if p:
            products.add(p)
            continue
        page = safe_url(href, source_url, 'listing')
        if page and page != source_url:
            pages.add(page)
    return products, pages



class ListingOfferParser(HTMLParser):
    """Pareia nome/link e preço principal SOMENTE quando aparecem em sequência.

    Uma âncora de produto inicia um cartão. Outro link de produto encerra o
    anterior. Valores fora dos primeiros 260 caracteres após o nome não valem.
    """
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.current_url = None
        self.inside_link = False
        self.anchor_words = []
        self.following = []
        self.pairs = []

    def finish(self):
        if not self.current_url:
            return
        name = re.sub(r'\s+', ' ', ' '.join(self.anchor_words)).strip()
        snippet = re.sub(r'\s+', ' ', ' '.join(self.following))[:260]
        matches = list(re.finditer(r'\bPor\s*R\$\s*([1-9]\d{0,2}(?:\.\d{3})*,\d{2})', snippet, re.I))
        if len(matches) == 1 and 9 <= len(name) <= 180:
            self.pairs.append((self.current_url, name, matches[0].group(1)))

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        url = safe_url(dict(attrs).get('href'), self.page_url, 'product')
        if url:
            self.finish()
            self.current_url = url
            self.inside_link = True
            self.anchor_words = []
            self.following = []
        elif self.current_url:
            self.inside_link = False

    def handle_endtag(self, tag):
        if tag == 'a':
            self.inside_link = False

    def handle_data(self, data):
        if not self.current_url:
            return
        if self.inside_link:
            self.anchor_words.append(data)
        elif len(' '.join(self.following)) < 350:
            self.following.append(data)

    def close(self):
        super().close()
        self.finish()


def listing_offers(html, url, cfg):
    """Apenas Sonda: catálogo com nome, pacote e 'Por R$' explícitos."""
    if urlsplit(url).hostname != 'www.sondadelivery.com.br':
        return {}
    parser = ListingOfferParser(url)
    parser.feed(html)
    parser.close()
    found = {}
    for link, title, text_price in parser.pairs:
        try:
            identity = identify(title)
            price = coletar.br_price(text_price)
            if price is None:
                continue
            rec = {**identity, 'mercado':HOSTS['www.sondadelivery.com.br'],
                   'cidade':cfg['cidade_online'], 'uf':cfg['uf_online'],
                   'preco':f'{price:.2f}', 'atualizado':date.today().isoformat(), 'link':link}
            # Preço conflitante dentro da mesma página: não publica.
            if link in found and found[link]['preco'] != rec['preco']:
                found.pop(link, None)
            else:
                found[link] = {f:rec.get(f,'') for f in FIELDS}
        except (ValueError, KeyError):
            continue
    return found

def get_title(html, link):
    page = coletar.ProductPage()
    page.feed(html)
    slug = norm(unquote(urlsplit(link).path.split('/')[-1]))
    # Sonda tem o ID no final; para comparar com o nome use o segmento anterior.
    if slug.isnumeric():
        slug = norm(unquote(urlsplit(link).path.split('/')[-2]))
    tokens = {s for s in re.split(r'[^a-z0-9]+', slug) if len(s) > 3}
    options = []
    for h in page.heading_blocks:
        h = re.sub(r'\s+', ' ', h).strip()
        if not 9 <= len(h) <= 240 or not SIZE_RE.search(norm(h)):
            continue
        score = len(tokens.intersection(set(re.split(r'[^a-z0-9]+', norm(h)))))
        if score >= min(2, len(tokens)) and score >= 1:
            options.append((score, -len(h), h))
    if not options:
        raise ValueError('Título e embalagem não foram confirmados na página de produto')
    return max(options)[2]


def category(title):
    s = norm(title)
    if any(k in s for k in ("leite", "queijo", "iogurte", "manteiga", "requeij", "creme de leite")):
        return "Laticínios"
    if any(k in s for k in ("refrigerante", "suco", "agua mineral", "chá", "cha ", "café", "cafe")):
        return "Bebidas"
    if any(k in s for k in ("detergente", "sabao", "sabão", "desinfetante", "amaciante", "lava roupas", "água sanitária", "agua sanitaria")):
        return "Limpeza"
    if any(k in s for k in ("shampoo", "creme dental", "sabonete", "desodorante", "papel higienico", "absorvente")):
        return "Higiene"
    if any(k in s for k in ("frango", "carne", "bife", "linguica", "linguiça", "picanha", "hamburguer", "peito bovino")):
        return "Carnes"
    if any(k in s for k in ("banana", "maça", "maca", "tomate", "cebola", "batata", "laranja", "cenoura", "uva ")):
        return "Hortifruti"
    return "Mercearia"


def identify(title):
    """Identidade conservadora, embalagem unitária e marca sem suposição.

    Nomes desconhecidos mantêm descrição completa; só são comparáveis se iguais.
    Kits/multipacks sem quantidade inequívoca são descartados.
    """
    s = re.sub(r'\s+', ' ', title).strip()
    n = norm(s)
    if any(re.search(r'\b' + re.escape(word) + r'\b', n) for word in BLOCKED):
        raise ValueError('Categoria regulada/não alimentícia excluída do coletor')
    if re.search(r'\b(kit|combo|leve\s+\d+\s+pague|pague\s+\d+|\d+\s*x\s*\d+)\b', n):
        raise ValueError('Kit ou múltiplas embalagens não comparáveis com segurança')
    sizes = list(SIZE_RE.finditer(n))
    if len(sizes) != 1:
        raise ValueError('Embalagem ambígua (nenhuma ou várias quantidades)')
    match = sizes[0]
    size = float(match.group(1).replace(',', '.'))
    unit = UNITS[match.group(2)]
    if size <= 0 or size > 10000:
        raise ValueError('Embalagem fora de faixa')
    brand = None
    for b in sorted(BRANDS, key=len, reverse=True):
        if re.search(r'(?<!\w)' + re.escape(norm(b)) + r'(?!\w)', n):
            brand = b
            break
    if brand:
        # Elimina embalagem e marca da denominação, sem remover tipo/sabor.
        product = re.sub(r'\s+', ' ', re.sub(r'(?<!\w)' + re.escape(brand) + r'(?!\w)', ' ', s, flags=re.I))
        # Mais seguro: uma descrição truncada somente de tamanho e apresentação.
        product = re.sub(r'\b(?:pacote|pote|garrafa|caixa|lata|vidro|pet|sache|sachê)\b', ' ', product, flags=re.I)
        product = SIZE_RE.sub(' ', product)
        product = re.sub(r'\s+', ' ', product).strip(' -').strip()
        # Itens populares: agrupar apenas se mesma variedade, marca e embalagem.
        lowered = norm(s)
        if 'arroz' in lowered:
            if 'integral' in lowered: product = 'Arroz integral'
            elif 'parboilizado' in lowered: product = 'Arroz parboilizado'
            elif re.search(r'\b(branco|agulhinha)\b', lowered): product = 'Arroz branco'
        elif 'feijao' in lowered and 'carioca' in lowered: product = 'Feijão carioca'
        elif 'leite' in lowered and 'integral' in lowered and 'sem lactose' not in lowered: product = 'Leite integral'
    else:
        brand = 'Marca não identificada'
        product = re.sub(r'\s+', ' ', SIZE_RE.sub(' ', s)).strip(' -')
    if not product or len(product) < 3 or len(product) > 175:
        raise ValueError('Não foi possível isolar a identidade do produto')
    return {'produto':product, 'marca':brand, 'tamanho':int(size) if size.is_integer() else size,
            'unidade':unit, 'categoria':category(s)}


def extract_product(html, url, cfg):
    title = get_title(html, url)
    attrs = identify(title)
    # Para marcas não identificadas, a checagem de identidade é feita pelo
    # título completo e embalagem, não por uma marca inventada.
    source = dict(attrs, tipo='pao' if urlsplit(url).hostname == 'www.paodeacucar.com' else 'sonda')
    if attrs['marca'] == 'Marca não identificada':
        source['marca'] = title.split()[0]
        source['produto'] = title.split()[0]
    price = coletar.parse_price(html, source)
    record = {**attrs, 'mercado': HOSTS[urlsplit(url).hostname],
              'cidade': cfg['cidade_online'], 'uf':cfg['uf_online'],
              'preco':f'{price:.2f}', 'atualizado':date.today().isoformat(), 'link':url}
    return {f:record.get(f,'') for f in FIELDS}


def valid_recent(row, max_age_days, date_now=None):
    try:
        age = (date_now or date.today()) - date.fromisoformat(str(row.get('atualizado',''))[:10])
        return 0 <= age.days <= max_age_days and coletar.br_price(row.get('preco')) is not None
    except (TypeError, ValueError):
        return False


def read_csv(file):
    if not Path(file).exists():
        return []
    with Path(file).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(file, records):
    # Ordenação estável; sempre escreve um CSV válido mesmo sem ofertas.
    clean = [r for r in records if all(str(r.get(k, '')).strip() for k in ('produto','marca','tamanho','unidade','mercado','cidade','uf','preco','atualizado','link'))]
    clean.sort(key=lambda r:(norm(r['produto']),norm(r['marca']),str(r['tamanho']),r['mercado']))
    with Path(file).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(clean)


class Client:
    def __init__(self, delay):
        self.robot_cache = {}
        self.last = {}
        self.delay = max(float(delay), 2.5)
        self.blocked = set()
    def request(self, url):
        host = urlsplit(url).hostname
        if host in self.blocked:
            raise ValueError('Site suspenso nesta execução após erro de acesso')
        permitted, reason = coletar.allowed_by_robots(url, self.robot_cache)
        if not permitted:
            self.blocked.add(host) if 'robots' in reason.lower() else None
            raise ValueError(reason)
        # Mesmo domínio recebe no máximo uma nova consulta após delay.
        delta = time.monotonic() - self.last.get(host, 0)
        if delta < self.delay:
            time.sleep(self.delay - delta)
        self.last[host] = time.monotonic()
        try:
            return coletar.get_text(url)
        except HTTPError as exc:
            if exc.code in (401, 403, 429):
                self.blocked.add(host) # não força acesso com user agents/proxies
            raise


def bootstrap_catalog(data):
    data = data if isinstance(data, dict) else {}
    data.setdefault('versao', 1)
    data.setdefault('paginas', {})
    data.setdefault('produtos', {})
    for url in LIST_START:
        data['paginas'].setdefault(url, {'ultima_consulta':'', 'falhas':0})
    return data


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def run(config_path=None, base=None, client=None):
    base = Path(base or ROOT)
    cfg = load_json(config_path or base / 'config-expansao.json', {})
    def opt(k, default, mini, maxi):
        return min(maxi, max(mini, int(cfg.get(k, default))))
    pages_budget = opt('max_paginas_descoberta_por_execucao', 8, 0, 30)
    products_budget = opt('max_produtos_consultados_por_execucao', 180, 0, 400)
    max_products = opt('max_produtos_catalogo', 12000, 6, 50000)
    max_pages = opt('max_paginas_catalogo', 1200, 10, 5000)
    age_days = opt('dias_para_manter_preco_confirmado', 2, 0, 2)
    refresh_hours = opt('horas_para_reconsultar_produto', 18, 6, 144)
    page_refresh = opt('horas_para_reconsultar_pagina', 72, 24, 720)
    cfg.setdefault('cidade_online', 'São Paulo'); cfg.setdefault('uf_online', 'SP')
    data = bootstrap_catalog(load_json(base / 'catalogo.json', {}))
    products = data['produtos']; pages = data['paginas']
    client = client or Client(cfg.get('intervalo_minimo_por_site_segundos',3))
    started = now()
    errors = []
    added, touched, good = 0, 0, 0
    maximum_seconds = opt('max_duracao_execucao_minutos', 19, 3, 23) * 60
    clock_start = time.monotonic()
    # Descobre os novos links respeitando limite de páginas e robots.txt.
    queue = sorted(pages, key=lambda u:(parse_when(pages[u].get('ultima_consulta')), u))
    for url in queue[:pages_budget]:
        if time.monotonic() - clock_start > maximum_seconds: break
        p = pages[url]
        if now() - parse_when(p.get('ultima_consulta')) < timedelta(hours=page_refresh):
            continue
        try:
            html = client.request(url)
            links, more = discover(html, url)
            for link in sorted(links):
                if len(products) >= max_products: break
                if link not in products:
                    products[link] = {'ultima_consulta':'', 'falhas':0, 'registro':None}
                    added += 1
            # O nome e o preço precisam estar juntos na listagem pública.
            # Quando são claros, evita uma solicitação HTTP adicional.
            auto_prices = listing_offers(html, url, cfg)
            for link, record in auto_prices.items():
                if link in products:
                    products[link].update({'registro':record,'ultima_consulta':stamp(),'falhas':0})
            for link in sorted(more):
                if len(pages) >= max_pages: break
                pages.setdefault(link, {'ultima_consulta':'', 'falhas':0})
            p['falhas'] = 0
            print(f'DESCOBERTA: {urlsplit(url).hostname} {len(links)} links na página, {len(auto_prices)} ofertas com preço explícito; novos links no catálogo: {added}')
        except (HTTPError, URLError, ValueError, OSError, TimeoutError) as e:
            p['falhas'] = int(p.get('falhas',0)) + 1
            errors.append(f'lista: {url}: {type(e).__name__}: {str(e)[:110]}')
        finally:
            p['ultima_consulta'] = stamp()
            touched += 1
    # O coletor principal já renovou as seis fontes fixas nesta execução.
    # Somente fontes fixas do coletor principal; ofertas antigas do catálogo não podem
    # se tornar 'sementes' e sobreviver a uma tentativa de atualização malsucedida.
    seed_config = load_json(base / 'fontes.json', {})
    fixed_urls = {r['url'] for r in seed_config.get('fontes', []) if r.get('url')}
    base_rows = [r for r in read_csv(base / 'precos.csv') if r.get('link') in fixed_urls]
    base_urls = {r['link'] for r in base_rows}
    # Intercala mercados para milhares de URLs de uma rede não impedirem a outra.
    candidates = sorted(products, key=lambda u:(parse_when(products[u].get('ultima_consulta')), u))
    left = [u for u in candidates if urlsplit(u).hostname == 'www.paodeacucar.com']
    right = [u for u in candidates if urlsplit(u).hostname == 'www.sondadelivery.com.br']
    due = [u for pair in itertools.zip_longest(left, right) for u in pair if u]
    for url in due:
        if good >= products_budget or time.monotonic() - clock_start > maximum_seconds:
            break
        if urlsplit(url).hostname in getattr(client, 'blocked', set()):
            continue
        if url in base_urls:
            continue
        rec = products[url]
        if now() - parse_when(rec.get('ultima_consulta')) < timedelta(hours=refresh_hours):
            continue
        good += 1  # conta tentativa para jamais ultrapassar o teto
        try:
            html = client.request(url)
            row = extract_product(html, url, cfg)
            rec['registro'] = row
            rec['falhas'] = 0
        except (HTTPError, URLError, ValueError, OSError, TimeoutError, KeyError, TypeError) as e:
            rec['registro'] = None  # falha cancela oferta anterior em vez de republicá-la
            rec['falhas'] = int(rec.get('falhas',0)) + 1
            if len(errors) < 35:
                errors.append(f'produto: {url}: {type(e).__name__}: {str(e)[:110]}')
        finally:
            rec['ultima_consulta'] = stamp()
    valid = [r['registro'] for r in products.values() if isinstance(r.get('registro'),dict) and valid_recent(r['registro'],age_days)]
    by_url = {r['link']:r for r in valid}
    for row in base_rows:
        if valid_recent(row, age_days):
            by_url[row['link']] = row
    write_csv(base / 'precos.csv', by_url.values())
    status = load_json(base / 'status.json', {})
    status.update({
        'ultima_execucao_utc': stamp(), 'modo':'catalogo_incremental',
        'urls_catalogo':len(products), 'paginas_listagem':len(pages),
        'novos_links_descobertos':added, 'paginas_consultadas':touched,
        'produtos_consultados_nesta_expansao':good,
        'precos_coletados':len(by_url), 'ofertas_atualizadas_hoje':sum(x['atualizado']==date.today().isoformat() for x in by_url.values()),
        'fontes_indisponiveis_nesta_expansao':sum(1 for x in errors if x.startswith('produto:')),
        'avisos_expansao':errors[:35],
        'nota':'Quantidade de URLs descobertas não equivale a ofertas: só contam preços de página confirmada nos últimos três dias corridos (hoje e dois dias anteriores). Apenas preços online, sujeitos a CEP e disponibilidade; não reproduzir como preço de loja física.'})
    (base / 'catalogo.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n', encoding='utf-8')
    (base / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'RESUMO: {len(products)} URLs no catálogo, {good} tentativas de preço, {len(by_url)} ofertas recentes publicadas; {len(errors)} avisos.')
    return status


if __name__ == '__main__':
    run()
