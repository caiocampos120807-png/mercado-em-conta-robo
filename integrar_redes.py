#!/usr/bin/env python3
"""Conectores experimentais para Extra, Carrefour, Atacadão e Mambo.

Somente HTML público/JSON-LD/URLs de produto verificáveis. Respeita robots.txt,
sem cookies de usuário, APIs privadas, proxies, CAPTCHA, login ou CEP inventado.
Não publica preços sem vínculo inequívoco com a embalagem e a oferta.
A execução pode terminar verde com 0 preços adicionais: ver redes-status.json.

Stdlib Python 3.12. Integra as ofertas com precos.csv existente sem apagá-las.
"""
from __future__ import annotations

import csv
import html
import json
import re
import time
import unicodedata
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit, parse_qs
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

import coletar
import expandir_catalogo as exp

ROOT = Path(__file__).resolve().parent
FIELDS = coletar.FIELDS
USER_AGENT = coletar.AGENT
NETWORKS = {
    'www.extramercado.com.br': 'extra',
    'mercado.carrefour.com.br': 'carrefour',
    'www.atacadao.com.br': 'atacadao',
    'www.mambo.com.br': 'mambo',
}
MAX_HTML = 3_000_000
RE_PRICE = re.compile(r'R\$\s*([1-9]\d{0,3}(?:\.\d{3})*,\d{2})', re.I)
UNAVAILABLE = re.compile(r'\b(?:produto indispon[ií]vel|sem estoque|esgotado|out of stock)\b', re.I)


def utcnow():
    return datetime.now(timezone.utc)


def norm(text):
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(ch))


def safe_url(raw, base='', kind='product'):
    """Allowlist estrita: restringe URLs, caminhos e paginação sem tokens."""
    if not isinstance(raw, str) or len(raw) > 1400:
        return None
    try:
        u = urlsplit(urljoin(base, html.unescape(raw)))
    except ValueError:
        return None
    if u.scheme != 'https' or u.hostname not in NETWORKS or u.username or u.password or u.port:
        return None
    path = unquote(u.path)
    if '\\' in path or '/..' in path or '//' in path or len(path) > 600:
        return None
    host = u.hostname
    if kind == 'product':
        patterns = {
            'extra': r'/produto/\d+/[\w\-]+/?',
            'carrefour': r'/produto/[\w\-]+/?',
            'atacadao': r'/(?:produto|p)/[\w\-]+/?',
            'mambo': r'/[\w\-]+/p/?',
        }
        if not re.fullmatch(patterns[NETWORKS[host]], path, flags=re.I):
            return None
    elif kind == 'listing':
        patterns = {
            'extra': r'/(?:categoria/[\w\-/]+|especial/[\w\-]+)',
            'carrefour': r'/(?:categoria/[\w\-/]+|marca/[\w\-]+)',
            'atacadao': r'/(?:mercearia(?:/[\w\-]+){0,3}|catalogo)',
            'mambo': r'/(?:[\w\-]+)',
        }
        if not re.fullmatch(patterns[NETWORKS[host]], path.rstrip('/'), flags=re.I):
            return None
        if u.query:
            q = parse_qs(u.query, keep_blank_values=True)
            if set(q) != {'page'} or len(q['page']) != 1 or not re.fullmatch(r'\d{1,2}', q['page'][0]):
                return None
            if int(q['page'][0]) > 12:
                return None
            return urlunsplit(('https', host, u.path.rstrip('/'), f"page={int(q['page'][0])}", ''))
    else:
        return None
    if u.query or u.fragment:
        # Tracking and personalization params never follow links to product pages.
        return urlunsplit(('https', host, u.path.rstrip('/'), '', ''))
    return urlunsplit(('https', host, u.path.rstrip('/'), '', ''))


class HtmlProducts(HTMLParser):
    """Visible text, product anchors, title blocks and schema.org JSON-LD."""
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.texts = []
        self.headings = []
        self.heading = None
        self.script = None
        self.ld = []
        self.ignore = 0
        self.card = None
        self.in_anchor = False
        self.cards = []
        self.links = set()
        self.listings = set()

    def finish_card(self):
        if not self.card:
            return
        title = ' '.join(self.card['anchor']).strip()
        tail = ' '.join(self.card['after']).strip()
        self.cards.append((self.card['url'], re.sub(r'\s+', ' ', title), re.sub(r'\s+', ' ', tail)))
        self.card = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script':
            self.ignore += 1
            self.script = [] if str(a.get('type','')).lower() == 'application/ld+json' else None
            return
        if tag in {'style', 'noscript', 'svg'}:
            self.ignore += 1
            return
        if self.ignore:
            return
        if tag == 'a':
            href = a.get('href','')
            url = safe_url(href, self.source, 'product')
            if url:
                self.links.add(url)
                if self.card and self.card['url'] != url:
                    self.finish_card()
                if not self.card:
                    self.card = {'url':url, 'anchor':[], 'after':[]}
                self.in_anchor = True
            else:
                listing = safe_url(href, self.source, 'listing')
                if listing:
                    self.listings.add(listing)
                self.in_anchor = False
        elif tag == 'img' and self.card and self.in_anchor:
            alt = a.get('alt', '').strip()
            if 10 < len(alt) < 190:
                self.card['anchor'].append(alt)
        if tag in {'h1','h2'}:
            self.heading = []

    def handle_endtag(self, tag):
        if tag == 'script':
            if self.script is not None:
                self.ld.append(''.join(self.script))
            self.script = None
            self.ignore = max(0, self.ignore - 1)
            return
        if tag in {'style','noscript','svg'}:
            self.ignore = max(0, self.ignore - 1)
            return
        if self.ignore:
            return
        if tag == 'a':
            self.in_anchor = False
        if tag in {'h1','h2'} and self.heading is not None:
            heading = re.sub(r'\s+',' ',' '.join(self.heading)).strip()
            if heading:
                self.headings.append(heading)
            self.heading = None

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
            return
        if self.ignore:
            return
        data = html.unescape(str(data)).strip()
        if not data:
            return
        self.texts.append(data)
        if self.heading is not None:
            self.heading.append(data)
        if self.card:
            where = 'anchor' if self.in_anchor else 'after'
            if len(' '.join(self.card[where])) < (220 if where == 'anchor' else 420):
                self.card[where].append(data)

    def close(self):
        super().close()
        self.finish_card()

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.texts))


def iter_products(obj):
    if isinstance(obj, list):
        for i in obj:
            yield from iter_products(i)
    elif isinstance(obj, dict):
        typ = obj.get('@type','')
        types = typ if isinstance(typ,list) else [typ]
        if any(str(x).lower() == 'product' for x in types):
            yield obj
        for key in ('@graph','itemListElement','item','mainEntity','hasVariant'):
            if key in obj:
                yield from iter_products(obj[key])


def jsonld_offers(page, url):
    """Product with same page URL, current BRL offer and explicit availability."""
    for raw in page.ld:
        try: root=json.loads(raw)
        except (TypeError, json.JSONDecodeError): continue
        for obj in iter_products(root):
            u = obj.get('url','')
            if u and safe_url(u,url,'product') != url:
                continue
            offers = obj.get('offers',[])
            for offer in offers if isinstance(offers,list) else [offers]:
                if not isinstance(offer,dict): continue
                availability = str(offer.get('availability','')).lower()
                if any(x in availability for x in ('outofstock','discontinued','soldout')):
                    continue
                if availability and not any(x in availability for x in ('instock','limitedavailability','preorder')):
                    continue
                currency = offer.get('priceCurrency','BRL')
                if currency != 'BRL': continue
                raw_price = offer.get('price')
                if raw_price is None and isinstance(offer.get('priceSpecification'),dict):
                    raw_price = offer['priceSpecification'].get('price')
                price = coletar.br_price(raw_price)
                name = obj.get('name','')
                if price is not None and isinstance(name,str) and name.strip():
                    return name, price
    return None


def primary_price(text):
    """A single advertised price; never use unit prices, cart totals or crossed out MSRP."""
    s = re.sub(r'\s+', ' ', html.unescape(str(text)))
    s = re.split(r'\bPre[cç]o\s+por\s+(?:1\s*)?(?:kg|g|l|litro|unidade)\b',s,1,flags=re.I)[0]
    matches = list(RE_PRICE.finditer(s))
    if not matches:
        return None
    if len(matches) > 1:
        # Distinguish old and current prices only when the current is explicit.
        tagged = re.search(r'\b(?:por|pre[cç]o\s+(?:final|atual))\s*:?\s*R\$\s*([1-9]\d{0,3}(?:\.\d{3})*,\d{2})',s,re.I)
        if not tagged:
            return None
        return coletar.br_price(tagged.group(1))
    return coletar.br_price(matches[0].group(1))


def record(name, price, url, network, city='São Paulo', uf='SP'):
    if not network.get('localizacao_confirmada',False):
        raise ValueError('Rede exige loja/CEP confirmado; não publicar preço genérico')
    row=exp.identify(name)
    if row['marca'] == 'Marca não identificada':
        # A mesma descrição completa permanece comparável apenas se idêntica.
        pass
    if price is None or not (0.1 <= price <= 10000):
        raise ValueError('Preço indisponível')
    d={**row,'mercado':network['nome'], 'cidade':city, 'uf':uf, 'preco':f'{price:.2f}',
       'atualizado':date.today().isoformat(), 'link':url}
    return {k:d.get(k,'') for k in FIELDS}


def product_offer(page, source_url, network, city, uf):
    if UNAVAILABLE.search(page.text[:850]):
        raise ValueError('Produto indisponível')
    h1=next((x for x in page.headings if exp.SIZE_RE.search(norm(x))),None)
    structured=jsonld_offers(page,source_url)
    if structured:
        name, price=structured
        # JSON-LD sem título visível pode descrever recomendação, não produto principal.
        if not h1:
            raise ValueError('Oferta JSON-LD sem título do produto visível')
        shown, claimed = exp.identify(h1), exp.identify(name)
        if any(shown[k] != claimed[k] for k in ('produto', 'marca', 'tamanho', 'unidade')):
            raise ValueError('Produto, marca ou embalagem divergem entre título e JSON-LD')
        return record(name,price,source_url,network,city,uf)
    if not h1:
        raise ValueError('Título completo/embalagem indisponíveis')
    # Prefer the slice after the visible <h1> and before unit-price/freight text.
    whole=page.text
    offset=whole.find(h1)
    if offset < 0:
        raise ValueError('Título não encontrado')
    tail=whole[offset+len(h1):offset+len(h1)+400]
    tail=re.split(r'\b(?:Calcular o frete|Descri[cç][aã]o do produto|Recomendad[oa]s)\b',tail,maxsplit=1,flags=re.I)[0]
    price=primary_price(tail)
    return record(h1, price, source_url, network,city,uf)


def listing_offers(page, network,city,uf):
    """Only a tightly linked product <a> + clear adjacent BRL price."""
    found={}
    for url, title, tail in page.cards:
        if urlsplit(url).hostname != network['host']:
            continue
        # Anchor text itself must contain the product and exact package.
        name=title.split('R$')[0].strip()
        # Alguns cards mostram o mesmo título no ALT da foto e no texto.
        half=len(name)//2
        if half and name[:half].strip()==name[half:].strip():
            name=name[:half].strip()
        if len(name)<10 or len(name)>210:
            continue
        if UNAVAILABLE.search((title+' '+tail)[:180]):
            continue
        # If anchor has a price, it belongs to this product; otherwise first 170 chars of following text.
        after = title[len(name):] if 'R$' in title else tail[:170]
        try:
            price=primary_price(after)
            if price is None:
                continue
            row=record(name,price,url,network,city,uf)
            if url in found and found[url]['preco'] != row['preco']:
                found.pop(url,None)  # ambiguous duplicate listing
            else: found[url]=row
        except (TypeError, ValueError, KeyError):
            continue
    return found


class SafeClient:
    """robots.txt fail-closed, lower request rate, stop host on access denial."""
    def __init__(self, delay=4, opener=urlopen):
        self.delay=max(3.5,float(delay))
        self.opener=opener
        self.robots={}
        self.last={}
        self.disabled=set()

    def robot_policy(self, url):
        u=urlsplit(url)
        root=f'https://{u.hostname}'
        if root not in self.robots:
            try:
                req=Request(root+'/robots.txt',headers={'User-Agent':USER_AGENT})
                with self.opener(req,timeout=14) as r:
                    if urlsplit(r.url).hostname != u.hostname: raise ValueError('robots redirecionou para outro host')
                    txt=r.read(450_001)
                    if len(txt)>450_000: raise ValueError('robots muito grande')
                parser=RobotFileParser()
                parser.parse(txt.decode('utf-8',errors='replace').splitlines())
                self.robots[root]=parser
            except HTTPError as e:
                self.robots[root]=True if e.code==404 else False
            except (OSError,URLError,ValueError):
                self.robots[root]=False
        value=self.robots[root]
        if isinstance(value,bool): return value, self.delay
        permitted=value.can_fetch(USER_AGENT,url)
        return permitted,max(self.delay, float(value.crawl_delay(USER_AGENT) or 0))

    def get(self,url):
        if not safe_url(url,kind='product') and not safe_url(url,kind='listing'):
            raise ValueError('URL de rede não autorizada')
        host=urlsplit(url).hostname
        if host in self.disabled: raise ValueError('Host suspenso após bloqueio')
        ok, delay=self.robot_policy(url)
        if not ok:
            self.disabled.add(host)
            raise ValueError('robots.txt impede acesso ou está indisponível')
        wait=self.last.get(host,0)+delay-time.monotonic()
        if wait>0: time.sleep(wait)
        self.last[host]=time.monotonic()
        req=Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html,application/ld+json;q=0.8','Accept-Language':'pt-BR,pt;q=0.7'})
        try:
            with self.opener(req,timeout=18) as r:
                kind = 'product' if safe_url(url, kind='product') else 'listing'
                if safe_url(r.url, kind=kind) != safe_url(url, kind=kind):
                    raise ValueError('Redirecionamento para URL diferente, sem confirmação')
                content_type=str(r.headers.get('Content-Type','')).lower()
                if content_type and 'html' not in content_type:
                    raise ValueError('Tipo de resposta não HTML')
                raw=r.read(MAX_HTML+1)
                if len(raw)>MAX_HTML: raise ValueError('HTML acima do limite')
                enc=r.headers.get_content_charset() or 'utf-8'
                return raw.decode(enc,errors='replace')
        except HTTPError as e:
            if e.code in (401,403,429): self.disabled.add(host)
            raise


def load_json(path, default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def stamp():return utcnow().isoformat(timespec='seconds')


def when(raw):return exp.parse_when(raw)


def fair_queue(entries):
    """Round-robin by network, oldest-first within each network."""
    queues=defaultdict(list)
    for url, data in entries.items():
        host=urlsplit(url).hostname
        if host in NETWORKS: queues[host].append((when(data.get('last','')),url))
    for host, v in list(queues.items()):
        v.sort()
        queues[host]=deque(v)
    results=[]
    while any(queues.values()):
        for host in sorted(queues):
            if queues[host]: results.append(queues[host].popleft()[1])
    return results


def run(base=ROOT, config_path=None, client=None):
    base=Path(base)
    cfg=load_json(config_path or base/'redes-fontes.json',{})
    networks={net['host']:net for net in cfg.get('redes',[]) if net.get('host') in NETWORKS and net.get('id') == NETWORKS[net['host']]}
    limits=cfg.get('limites',{})
    def lim(key,default,lo,hi):return max(lo,min(hi,int(limits.get(key,default))))
    max_lists=lim('paginas_listagem_por_execucao',12,0,25)
    max_products=lim('paginas_produto_por_execucao',65,0,180)
    max_per=lim('max_links_por_rede',6000,100,20000)
    max_time=lim('max_duracao_minutos',10,2,20)*60
    age=lim('validade_preco_dias',2,0,2)
    hours_list=lim('intervalo_entre_listagens_horas',30,12,168)
    hours_product=lim('intervalo_entre_produtos_horas',21,12,120)
    client=client or SafeClient(limits.get('intervalo_minimo_por_dominio_segundos',4))
    city=str(cfg.get('cidade_online','São Paulo'))[:75]
    uf=str(cfg.get('uf_online','SP'))[:2].upper()
    state=load_json(base/'catalogo_redes.json', {'schema':1,'listagens':{},'produtos':{}})
    pages=state.setdefault('listagens',{})
    products=state.setdefault('produtos',{})
    for net in networks.values():
        for raw in net.get('listagens',[]):
            url=safe_url(raw,kind='listing')
            if url and urlsplit(url).hostname==net['host']:
                pages.setdefault(url,{'last':'','fail':0})
        for raw in net.get('produtos_iniciais',[]):
            url=safe_url(raw,kind='product')
            if url and urlsplit(url).hostname==net['host']:
                products.setdefault(url,{'last':'','fail':0,'row':None})
    started=time.monotonic()
    errors=[]; discovered=0; listing_hits=0; detail_hits=0; list_calls=0; detail_calls=0
    for url in fair_queue(pages):
        if list_calls>=max_lists or time.monotonic()-started>max_time: break
        host=urlsplit(url).hostname
        if host not in networks:continue
        entry=pages[url]
        if utcnow()-when(entry.get('last')) < timedelta(hours=hours_list):continue
        list_calls+=1
        try:
            page=HtmlProducts(url);page.feed(client.get(url));page.close()
            net=networks[host]
            # Product links may be discovered even when this network has no visible price.
            max_at_host=sum(1 for x in products if urlsplit(x).hostname==host)
            for link in sorted(page.links):
                if max_at_host>=max_per:break
                if link not in products:
                    products[link]={'last':'','fail':0,'row':None};discovered+=1;max_at_host+=1
            for link in sorted(page.listings):
                if len(pages)>1500:break
                if link not in pages and urlsplit(link).hostname==host:
                    pages[link]={'last':'','fail':0}
            found=listing_offers(page,net,city,uf)
            for link,row in found.items():
                if link in products:
                    products[link].update({'row':row,'last':stamp(),'fail':0})
                    listing_hits+=1
            entry['fail']=0
            print(f'REDE {net["id"]}: listagem {len(page.links)} links, {len(found)} preços confirmados')
        except (HTTPError,URLError,OSError,ValueError,TimeoutError) as e:
            entry['fail']=min(1000,int(entry.get('fail',0))+1)
            if len(errors)<45:errors.append(f'listagem {NETWORKS.get(host,host)}: {type(e).__name__}: {str(e)[:110]}')
        finally:entry['last']=stamp()
    for url in fair_queue(products):
        if detail_calls>=max_products or time.monotonic()-started>max_time:break
        host=urlsplit(url).hostname
        if host not in networks:continue
        net=networks[host]
        if host in getattr(client,'disabled',set()):continue
        # Unknown locality must never leak a fake 'São Paulo' price.
        if not net.get('localizacao_confirmada',False):continue
        item=products[url]
        if utcnow()-when(item.get('last'))<timedelta(hours=hours_product):continue
        detail_calls+=1
        try:
            page=HtmlProducts(url);page.feed(client.get(url));page.close()
            row=product_offer(page,url,net,city,uf)
            item.update({'row':row,'fail':0})
            detail_hits+=1
        except (HTTPError,URLError,OSError,ValueError,TimeoutError,KeyError,TypeError) as e:
            item.update({'row':None,'fail':min(1000,int(item.get('fail',0))+1)})
            if len(errors)<45:errors.append(f'produto {NETWORKS.get(host,host)}: {type(e).__name__}: {str(e)[:110]}')
        finally:item['last']=stamp()
    # Inputs from the first two collectors are never discarded.
    rows=exp.read_csv(base/'precos.csv')
    final={r['link']:r for r in rows if exp.valid_recent(r,age) and isinstance(r.get('link'),str) and r.get('link')}
    for item in products.values():
        row=item.get('row')
        if isinstance(row,dict) and exp.valid_recent(row,age):
            final[row['link']]=row
    exp.write_csv(base/'precos.csv',final.values())
    breakdown={}
    for host,net in networks.items():
        real=[r for r in final.values() if urlsplit(r['link']).hostname==host]
        breakdown[net['id']]={'nome':net['nome'],'urls_descobertas':sum(urlsplit(u).hostname==host for u in products),
                              'precos_validos':len(real),'estado':'com preços confirmados' if real else 'sem preço confirmado',
                              'localizacao_exigida':not bool(net.get('localizacao_confirmada',False))}
    status={'gerado_em_utc':stamp(),'redes_candidatas':len(networks),'novos_links_descobertos':discovered,
            'paginas_listagem_consultadas':list_calls,'paginas_produto_consultadas':detail_calls,
            'ofertas_na_lista':listing_hits,'ofertas_na_pagina':detail_hits,
            'precos_ativos_total':len(final),'redes':breakdown,'avisos':errors,
            'nota':'Redes candidatas NÃO são mercados com preços disponíveis. Preços online, sujeitos a loja/CEP. Bloqueio, ausência de preço e estoque desconhecido nunca geram ofertas fictícias.'}
    (base/'catalogo_redes.json').write_text(json.dumps(state,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8')
    (base/'redes-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    old=load_json(base/'status.json',{})
    old.update({'redes_adicionais':status,'precos_coletados':len(final),'ultima_execucao_utc':status['gerado_em_utc']})
    (base/'status.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'REDES NOVAS: {len(networks)} conectores, {discovered} novos links, '
          f'{listing_hits+detail_hits} ofertas confirmadas nesta etapa, {len(final)} preços recentes totais.')
    return status

if __name__=='__main__':
    run()
