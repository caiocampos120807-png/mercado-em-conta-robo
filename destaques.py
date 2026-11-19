#!/usr/bin/env python3
"""Gera comparações locais verificáveis e texto editorial, sem inventar promoções.

Fontes: preços existentes e validados em precos.csv. Se 2 redes não tiverem o
mesmo produto/embalagem na mesma cidade, não há destaque.
Sem chamadas à rede nem bibliotecas de terceiros.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from gerar_indicadores import audit_row, normal, sku_key, authorized_hosts

BASE = Path(__file__).resolve().parent
MAX_PER_CITY = 20
MAX_GLOBAL = 160


def build(base=BASE, today=None):
    base=Path(base)
    today=today or date.today()
    with (base/'precos.csv').open(encoding='utf-8-sig', newline='') as file:
        original=list(csv.DictReader(file))
    # Mesma URL com preços contraditórios no mesmo lote => descartar todas.
    trusted_hosts=authorized_hosts(base)
    by_url={}
    conflicts=set()
    rejected=0
    for raw in original:
        row, reason=audit_row(raw, today,trusted_hosts)
        if row is None:
            rejected+=1
            continue
        url=row['link']
        if url in by_url and (by_url[url]['preco']!=row['preco'] or sku_key(by_url[url])!=sku_key(row)):
            conflicts.add(url)
        else:
            by_url[url]=row
    for url in conflicts:
        by_url.pop(url,None)
    grouped=defaultdict(lambda:defaultdict(list))
    for row in by_url.values():
        try:
            city=f"{row['cidade'].strip()} / {row['uf'].strip().upper()}"
            grouped[city][sku_key(row)].append(row)
        except (KeyError,ValueError):
            rejected+=1
    output=[]
    cities=[]
    for city, products in sorted(grouped.items()):
        city_results=[]
        for sku, rows in products.items():
            markets={}
            for row in rows:
                key=normal(row['mercado'])
                # Várias páginas do mesmo supermercado não viram várias redes.
                if key not in markets or row['preco']<markets[key]['preco']:
                    markets[key]=row
            if len(markets)<2:
                continue
            offers=sorted(markets.values(),key=lambda r:(r['preco'],r['mercado']))
            cheap,expensive=offers[0],offers[-1]
            difference=round(expensive['preco']-cheap['preco'],2)
            if difference<=0:
                continue
            city_results.append({
                'sku':sku,'cidade':city,'produto':cheap['produto'],
                'marca':cheap['marca'],'tamanho':cheap['tamanho'],
                'unidade':cheap['unidade'],'preco_menor':cheap['preco'],
                'mercado_menor':cheap['mercado'],'link_menor':cheap['link'],
                'preco_maior':expensive['preco'],'mercado_maior':expensive['mercado'],
                'link_maior':expensive['link'],'diferenca':difference,
                'quantidade_mercados':len(markets),'atualizado':min(r['atualizado'] for r in (cheap,expensive))
            })
        city_results.sort(key=lambda r:(-r['diferenca'],r['produto'].lower()))
        cities.append({'cidade':city,'comparacoes_com_diferenca':len(city_results)})
        output.extend(city_results[:MAX_PER_CITY])
    output=output[:MAX_GLOBAL]
    result={
        'schema':1,'gerado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'data_referencia':today.isoformat(),'comparacoes':output,'cidades':cities,
        'ofertas_rejeitadas':rejected+len(conflicts),
        'observacao':'Diferença entre preços coletados no mesmo dia ou nos dois dias anteriores, para o mesmo produto, marca e embalagem na mesma cidade. Não é desconto nem economia garantida. Pode depender de CEP, estoque e fidelidade.'
    }
    (base/'destaques.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[
        '# Comparações da semana — Mercado em Conta',
        '',f'Dados de referência: {today.strftime("%d/%m/%Y")}.',
        '', 'Valores observados em páginas de supermercados; sujeitos a CEP, estoque e alterações. ',
        'A diferença de preço **não é** desconto ou economia realizada.', ''
    ]
    if not output:
        lines+=['Nenhuma comparação com diferença de preço foi confirmada nesta execução.']
    for city in dict.fromkeys(item['cidade'] for item in output):
        lines+=['',f'## {city}','']
        for item in (x for x in output if x['cidade']==city):
            lines.append(f"- {item['produto']} {item['marca']} {item['tamanho']}{item['unidade']}: R$ {item['preco_menor']:.2f} em {item['mercado_menor']}; R$ {item['preco_maior']:.2f} em {item['mercado_maior']}. Diferença R$ {item['diferenca']:.2f}. Fontes: {item['link_menor']} | {item['link_maior']}")
    (base/'boletim-compartilhavel.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f"DESTAQUES: {len(output)} comparações de preços locais com diferença, {len(cities)} cidade(s), {len(conflicts)} URL(s) contraditória(s) descartada(s).")
    return result

if __name__=='__main__':
    build()
