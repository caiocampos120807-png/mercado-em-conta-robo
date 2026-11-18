#!/usr/bin/env python3
"""Auditoria e histórico de preços confirmados, somente biblioteca padrão.

Esta etapa NÃO altera precos.csv e NÃO inventa ofertas. Guarda snapshots
confirmados, limites de tamanho, resumos de cobertura e alertas de qualidade.
"""
from __future__ import annotations

import csv
import json
import math
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
ALLOWED = {'www.paodeacucar.com', 'www.sondadelivery.com.br', 'www.extramercado.com.br', 'mercado.carrefour.com.br', 'www.atacadao.com.br', 'www.mambo.com.br'}
UNITS = {'kg', 'g', 'ml', 'l', 'un'}
MAX_AGE_DAYS = 2
HISTORY_DAYS = 75
MAX_SERIES = 55
MAX_SERIES_TOTAL = 40000
MAX_PRODUCTS = 12000
FIELDS = {'produto','marca','tamanho','unidade','categoria','mercado','cidade','uf','preco','atualizado','link'}


def normal(text):
    s = unicodedata.normalize('NFKD', str(text or '').lower())
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())


def as_float(raw):
    v = str(raw or '').strip().replace('R$', '').replace(' ', '')
    if ',' in v and '.' in v:
        v = v.replace('.', '').replace(',', '.') if v.rfind(',') > v.rfind('.') else v.replace(',', '')
    elif ',' in v:
        v = v.replace(',', '.')
    try:
        value = float(v)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) and 0 < value <= 10000 else None


def quantity(size, unit):
    n = as_float(size)
    if n is None or n > 100000 or unit not in UNITS:
        return None
    return n * (1000 if unit in {'kg','l'} else 1)


def sku_key(row):
    # Igualdade estrita: nome, marca e quantidade física (g/ml/un).
    unit = str(row.get('unidade','')).lower().strip()
    kind = 'massa' if unit in {'kg','g'} else 'volume' if unit in {'l','ml'} else 'unidades'
    qty = quantity(row.get('tamanho'), unit)
    if not qty:
        raise ValueError('quantidade inválida')
    return '|'.join([normal(row['produto']),normal(row['marca']),kind,format(qty,'.9g')])


def audit_row(row, today=None):
    now = today or date.today()
    if not FIELDS.issubset(row):
        return None, 'campos ausentes'
    if not all(str(row.get(k,'')).strip() for k in ('produto','marca','tamanho','unidade','mercado','cidade','uf','preco','atualizado','link')):
        return None, 'campo obrigatório vazio'
    try:
        dt = date.fromisoformat(str(row['atualizado'])[:10])
    except ValueError:
        return None, 'data inválida'
    if not 0 <= (now-dt).days <= MAX_AGE_DAYS:
        return None, 'preço fora da validade'
    p = as_float(row['preco'])
    if p is None:
        return None, 'preço inválido'
    u = str(row['unidade']).strip().lower()
    if u not in UNITS or quantity(row['tamanho'],u) is None:
        return None, 'embalagem inválida'
    url = urlsplit(str(row['link']))
    if url.scheme != 'https' or url.hostname not in ALLOWED or url.username or url.password or url.port:
        return None, 'fonte não autorizada'
    if len(str(row['produto'])) > 240 or len(str(row['marca'])) > 150:
        return None, 'título excessivo'
    return {**row, 'preco': round(p,2), 'unidade':u, 'atualizado':dt.isoformat(), 'link':url.geturl()}, ''


def read_json(path, default):
    try:
        d=json.loads(Path(path).read_text(encoding='utf8'))
        return d if isinstance(d,dict) else default
    except (FileNotFoundError,ValueError,OSError):
        return default


def run(base=BASE, today=None):
    base=Path(base)
    today=today or date.today()
    source=base/'precos.csv'
    if not source.exists():
        raise FileNotFoundError('precos.csv ainda não existe')
    with source.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not FIELDS.issubset(reader.fieldnames):
            raise ValueError('precos.csv inválido: colunas obrigatórias ausentes')
        input_rows=list(reader)
    unique={}
    errors=defaultdict(int)
    for row in input_rows:
        valid, reason=audit_row(row,today)
        if not valid:
            errors[reason]+=1
            continue
        url=valid['link']
        old=unique.get(url)
        if old and old['preco']!=valid['preco']:
            # Duas ofertas conflitantes para o mesmo URL: recusar a fonte.
            unique[url]=None
            errors['conflito de URL']+=1
        elif url not in unique:
            unique[url]=valid
    confirmed=[r for r in unique.values() if r]
    bysku=defaultdict(list)
    for row in confirmed:
        try: bysku[sku_key(row)].append(row)
        except ValueError: errors['SKU inválido']+=1
    # Limite de histórico impede crescimento sem fim do repositório público.
    previous=read_json(base/'historico.json',{'schema':1,'products':{}})
    old_products=previous.get('products',{}) if isinstance(previous.get('products',{}),dict) else {}
    cutoff=(today-timedelta(days=HISTORY_DAYS)).isoformat()
    hist={}
    for key in set(old_products).union(bysku):
        past=old_products.get(key,{})
        offers=past.get('offers',{}) if isinstance(past,dict) else {}
        valid_offers={}
        for url, item in offers.items():
            if urlsplit(url).hostname not in ALLOWED or not isinstance(item,dict):
                continue
            samples=[s for s in item.get('serie',[]) if isinstance(s,dict) and isinstance(s.get('data'),str) and cutoff<=s['data']<=today.isoformat() and as_float(s.get('preco'))]
            samples.sort(key=lambda s:s['data'])
            valid_offers[url]={'mercado':str(item.get('mercado',''))[:120], 'serie':samples[-MAX_SERIES:]}
        for row in bysku.get(key,[]):
            url=row['link']
            item=valid_offers.setdefault(url,{'mercado':row['mercado'],'serie':[]})
            item['mercado']=row['mercado']
            bydate={s['data']:s for s in item['serie']}
            bydate[row['atualizado']]={'data':row['atualizado'],'preco':row['preco']}
            item['serie']=[bydate[d] for d in sorted(bydate) if d>=cutoff][-MAX_SERIES:]
        valid_offers={url:item for url,item in valid_offers.items() if item['serie']}
        if valid_offers:
            if bysku.get(key):
                chosen=bysku[key][0]
                attrs={k:chosen.get(k,'') for k in ('produto','marca','tamanho','unidade','categoria')}
            else:
                attrs={k:past.get(k,'') for k in ('produto','marca','tamanho','unidade','categoria')}
            hist[key]={**attrs,'offers':valid_offers}
    # Mantém primeiro os SKUs mais recentemente confirmados e limita volume global.
    def newest(item):
        return max((s['data'] for offer in item['offers'].values() for s in offer['serie']),default='')
    ordered=sorted(hist.items(),key=lambda kv:newest(kv[1]),reverse=True)[:MAX_PRODUCTS]
    limited={}
    total_samples=0
    for key, product in ordered:
        accepted={}
        for url, offer in product['offers'].items():
            remaining=MAX_SERIES_TOTAL-total_samples
            if remaining<=0: break
            samples=offer['serie'][-remaining:]
            accepted[url]={**offer,'serie':samples}
            total_samples+=len(samples)
        if accepted:
            limited[key]={**product,'offers':accepted}
        if total_samples>=MAX_SERIES_TOTAL: break
    brands=len({normal(r['marca']) for r in confirmed})
    markets=len({normal(r['mercado']) for r in confirmed})
    comparable=sum(len({normal(r['mercado']) for r in rows})>=2 for rows in bysku.values())
    robot_status=read_json(base/'status.json',{})
    report={
        'urls_catalogo':robot_status.get('urls_catalogo',0),
        'paginas_listagem':robot_status.get('paginas_listagem',0),
        'schema':1, 'gerado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'data_referencia':today.isoformat(),
        'ofertas_ativas':len(confirmed),
        'produtos_distintos':len(bysku),
        'produtos_em_2_ou_mais_mercados':comparable,
        'supermercados':markets,'marcas':brands,
        'ofertas_rejeitadas':sum(errors.values()),'motivos_rejeicao':dict(errors),
        'observacoes_historicas':total_samples,
        'nota':'Preços de páginas públicas, sujeitos a CEP, entrega, loja e alteração. Comparabilidade por nome/marca/embalagem EXATOS. Ofertas vencidas são omitidas.'}
    (base/'historico.json').write_text(json.dumps({'schema':1,'gerado_em_utc':report['gerado_em_utc'],'products':limited},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    (base/'indicadores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"AUDITORIA: {report['ofertas_ativas']} ofertas válidas, {report['produtos_distintos']} SKUs, {comparable} comparáveis em 2+ mercados, {report['ofertas_rejeitadas']} descartadas.")
    return report

if __name__=='__main__':
    run()
