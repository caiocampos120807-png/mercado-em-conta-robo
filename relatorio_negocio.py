#!/usr/bin/env python3
"""Indicadores verificáveis por cidade/mercado para planejamento comercial.

Usa exclusivamente precos.csv validado; não mede tráfego, clientes ou receita.
Não altera o catálogo ou o arquivo principal de ofertas.
"""
from __future__ import annotations
import csv
import json
from collections import defaultdict, Counter
from datetime import date, datetime, timezone
from pathlib import Path
from gerar_indicadores import audit_row, sku_key

BASE = Path(__file__).resolve().parent


def construir(base=BASE, hoje=None):
    base=Path(base)
    hoje=hoje or date.today()
    path=base/'precos.csv'
    if not path.exists():
        raise FileNotFoundError('precos.csv não encontrado')
    with path.open(newline='',encoding='utf-8-sig') as f:
        raw=list(csv.DictReader(f))
    valid=[]
    invalid=Counter()
    for r in raw:
        row,reason=audit_row(r,hoje)
        if row:valid.append(row)
        else:invalid[reason]+=1
    # Colisões no mesmo URL não viram duas ofertas distintas.
    urls={}
    conflicts=set()
    for r in valid:
        url=r['link']
        if url in urls and urls[url]['preco']!=r['preco']:
            conflicts.add(url)
        else:
            urls[url]=r
    for url in conflicts:urls.pop(url,None)
    valid=list(urls.values())
    regions=defaultdict(lambda:defaultdict(set))
    products=defaultdict(lambda:defaultdict(set))
    categories=Counter()
    for r in valid:
        location=f"{r['cidade'].strip()} / {r['uf'].strip().upper()}"
        market=r['mercado'].strip()
        key=sku_key(r)
        regions[location][market].add(key)
        products[location][key].add(market)
        categories[r.get('categoria','Outros').strip() or 'Outros']+=1
    markets=Counter(r['mercado'].strip() for r in valid)
    by_location=[]
    for city,store_skus in sorted(regions.items()):
        comparable=sum(len(stores)>1 for stores in products[city].values())
        by_location.append({'cidade':city,'mercados_com_preco':len(store_skus),
                            'produtos_distintos':len(products[city]),
                            'produtos_comparaveis':comparable,
                            'ofertas':sum(1 for r in valid if f"{r['cidade'].strip()} / {r['uf'].strip().upper()}"==city),
                            'mercados':[{'nome':market,'skus':len(skus)} for market,skus in sorted(store_skus.items())]})
    output={'schema':1,'gerado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'data_referencia':hoje.isoformat(),
            'ofertas_validadas':len(valid),'produtos_distintos_total':len(set(sku_key(r) for r in valid)),
            'mercados_com_precos':len(markets),
            'comparacoes_possiveis_por_cidade':sum(c['produtos_comparaveis'] for c in by_location),
            'cidades':by_location,
            'mercados':[{'nome':m,'ofertas':n} for m,n in sorted(markets.items(),key=lambda kv:(-kv[1],kv[0]))],
            'categorias':[{'nome':name,'ofertas':count} for name,count in categories.most_common(30)],
            'registros_rejeitados':sum(invalid.values())+len(conflicts),
            'limites':'Métricas de catálogo, não de usuários. Não incluem preços sem confirmação ou antigos. Comparáveis exigem mesmo SKU e mesma cidade.'}
    (base/'relatorio_negocio.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"NEGÓCIO: {len(valid)} ofertas, {len(markets)} mercados, {len(by_location)} cidades, {output['comparacoes_possiveis_por_cidade']} comparações regionais.")
    return output


if __name__=='__main__': construir()
