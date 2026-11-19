#!/usr/bin/env python3
"""Prioridades para a compra mensal de uma família de quatro pessoas.

A prioridade serve para ordenar *consultas*, nunca para inventar preço,
marca, embalagem ou quantidade que um mercado não publicou.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

# Relevância estimada, não estatística de consumo. Ajustável por família.
# Itens parecidos são deliberadamente específicos para evitar falsos acertos.
ITEMS = [
    ('Arroz', r'\barroz\b', 100),
    ('Feijão', r'\bfeijao\b', 100),
    ('Leite UHT', r'\bleite\b(?!\s+(?:condensado|em po|de coco|de amendoas))', 100),
    ('Café', r'\bcafe\b(?!\s+(?:da manha|com leite))', 100),
    ('Óleo de cozinha', r'\boleo\b\s+(?:de\s+)?(?:soja|girassol|canola|milho)', 100),
    ('Açúcar', r'\bacucar\b', 90),
    ('Macarrão', r'\bmacarrao\b|\bmassa\b\s+(?:espaguete|parafuso)', 95),
    ('Ovos', r'\bovos?\b\s+(?:de\s+)?galinha|\bovos?\b\s+(?:brancos?|vermelhos?)', 95),
    ('Frango', r'\bfrango\b|\bpeito\b\s+de\s+frango', 95),
    ('Carne bovina', r'\b(?:patinho|acem|coxao mole|coxao duro|carne moida)\b', 95),
    ('Sal', r'\bsal\b\s+(?:refinado|iodado|marinho|grosso)|\bsal\b$', 85),
    ('Farinha de trigo', r'\bfarinha\s+de\s+trigo\b', 85),
    ('Farinha de mandioca', r'\bfarinha\s+de\s+mandioca\b', 68),
    ('Molho de tomate', r'\bmolho\s+de\s+tomate\b|\bextrato\s+de\s+tomate\b', 82),
    ('Pão de forma', r'\bpao\s+de\s+forma\b', 85),
    ('Manteiga ou margarina', r'\b(?:manteiga|margarina)\b', 78),
    ('Queijo', r'\b(?:mussarela|mucarela|mu[cç]arela|queijo prato|queijo minas)\b', 75),
    ('Iogurte', r'\biogurte\b', 65),
    ('Batata', r'\bbatata\b(?!\s+(?:frita|chips|palha))', 75),
    ('Cebola', r'\bcebola\b', 75),
    ('Tomate', r'\btomate\b(?!\s+(?:seco|pelado|molho))', 75),
    ('Alho', r'\balho\b', 70),
    ('Banana', r'\bbanana\b', 75),
    ('Maçã', r'\bmaca\b', 70),
    ('Laranja', r'\blaranja\b(?!\s+refrigerante)', 70),
    ('Cenoura', r'\bcenoura\b', 67),
    ('Alface', r'\balface\b', 65),
    ('Papel higiênico', r'\bpapel\s+higienico\b', 95),
    ('Detergente', r'\bdetergente\b', 90),
    ('Sabão em pó ou líquido', r'\bsabao\b\s+(?:em\s+po|liquido|para\s+roupas)', 88),
    ('Água sanitária', r'\bagua\s+sanitaria\b', 80),
    ('Desinfetante', r'\bdesinfetante\b', 75),
    ('Esponja', r'\besponja\b', 70),
    ('Amaciante', r'\bamaciante\b', 60),
    ('Sabonete', r'\bsabonete\b', 90),
    ('Pasta de dente', r'\bcreme\s+dental\b|\bpasta\s+de\s+dente\b', 90),
    ('Shampoo', r'\bshampoo\b|\bxampu\b', 75),
    ('Desodorante', r'\bdesodorante\b', 70),
    ('Papel toalha', r'\bpapel\s+toalha\b', 50),
    ('Biscoito', r'\bbiscoito\b|\bbolacha\b', 55),
    ('Aveia', r'\baveia\b', 55),
    ('Água mineral', r'\bagua\s+mineral\b', 60),
    ('Cereal matinal', r'\bcereal\s+matinal\b|\bflocos\s+de\s+milho\b', 50),
]


def norm(value):
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value).lower())
                   if not unicodedata.combining(ch))


def families(text):
    s = norm(str(text)).replace('-', ' ').replace('_', ' ')
    s = re.sub(r'\s+', ' ', s)
    return [(name, weight) for name, regex, weight in ITEMS if re.search(regex, s)]


def priority(text):
    return max((weight for _, weight in families(text)), default=0)


def sku(row):
    """Chave restritiva; não mistura embalagem, marca nem variantes."""
    return '|'.join(norm(row.get(k, '')).strip() for k in ('produto', 'marca', 'tamanho', 'unidade'))


def other_market_skus(rows):
    result = defaultdict(set)
    for row in rows:
        if isinstance(row, dict) and all(row.get(k) for k in ('produto','marca','tamanho','unidade','mercado')):
            result[sku(row)].add(norm(row['mercado']))
    return result


def score_product(url, entry, verified_rows=()):
    """Maior nota => consulta primeiro; apenas ordenação, nunca afirma disponibilidade."""
    desc = unquote(urlsplit(url).path).replace('-', ' ').replace('_', ' ')
    row = entry.get('row') if isinstance(entry, dict) else None
    if isinstance(row, dict):
        desc += ' ' + ' '.join(str(row.get(k,'')) for k in ('produto','marca'))
    score = priority(desc)
    if isinstance(row, dict) and row.get('produto'):
        key=sku(row)
        markets=other_market_skus(verified_rows).get(key,set())
        if markets and norm(row.get('mercado','')) not in markets:
            score += 90
    else:
        # Bons candidatos a duplicação: mesma classe, marca e pacote visíveis na URL.
        chunks=set(norm(desc).split())
        for existing in verified_rows:
            if not isinstance(existing,dict) or not existing.get('marca'):continue
            brand=norm(existing['marca'])
            if brand in ('marca nao identificada','') or not set(brand.split()).issubset(chunks):continue
            if priority(existing.get('produto',''))<75:continue
            if priority(desc)!=priority(existing['produto']):continue
            size=norm(str(existing.get('tamanho','')))
            unit=norm(str(existing.get('unidade','')))
            if size and unit and re.search(r'(?<!\d)'+re.escape(size)+r'\s*'+re.escape(unit)+r'\b',norm(desc)):
                score+=65;break
    return score


def prioritize_queue(urls, state, verified_rows=()):
    return sorted(urls, key=lambda url:(-score_product(url, state.get(url,{}), verified_rows),
                                        str(state.get(url,{}).get('last','')),url))


def report(rows):
    results=defaultdict(lambda: {'ofertas':0, 'mercados':set()})
    for row in rows:
        text=' '.join(str(row.get(k,'')) for k in ('produto','marca'))
        matches=families(text)
        if not matches:continue
        name=matches[0][0]
        results[name]['ofertas']+=1
        results[name]['mercados'].add(str(row.get('mercado','')))
    return [{'item':name,'ofertas':v['ofertas'],'mercados':len(v['mercados'])}
            for name,_,_ in ITEMS for v in [results.get(name)] if v]
