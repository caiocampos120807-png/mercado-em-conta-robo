#!/usr/bin/env python3
"""Relatório público de qualidade e disponibilidade da coleta.

Não consulta supermercados, não inventa preços, não calcula visitantes.
Opera exclusivamente sobre precos.csv, validando os dados com as mesmas
regras do relatório comercial do projeto.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from gerar_indicadores import audit_row, sku_key, normal, authorized_hosts

BASE = Path(__file__).resolve().parent


def montar(base=BASE, hoje=None):
    base = Path(base)
    hoje = hoje or date.today()
    arquivo = base / 'precos.csv'
    if not arquivo.exists():
        raise FileNotFoundError('precos.csv não encontrado')
    with arquivo.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('precos.csv sem cabeçalho')
        originais = list(reader)
    trusted_hosts=authorized_hosts(base)
    rejeicoes = Counter()
    by_url = {}
    conflitantes = set()
    for original in originais:
        row, motivo = audit_row(original, hoje,trusted_hosts)
        if row is None:
            rejeicoes[motivo] += 1
            continue
        url = row['link']
        if url in by_url:
            prev = by_url[url]
            if (prev['preco'] != row['preco'] or sku_key(prev) != sku_key(row)
                    or normal(prev['cidade']) != normal(row['cidade'])):
                conflitantes.add(url)
        else:
            by_url[url] = row
    for url in conflitantes:
        by_url.pop(url, None)
    if conflitantes:
        rejeicoes['URL contraditória'] += len(conflitantes)
    validas = list(by_url.values())
    by_city_sku = defaultdict(lambda: defaultdict(set))
    by_market = defaultdict(lambda: {'ofertas': 0, 'cidades': set(), 'mais_recente': ''})
    datas = Counter()
    for row in validas:
        key = f"{row['cidade'].strip()} / {row['uf'].strip().upper()}"
        market = row['mercado'].strip()
        by_city_sku[key][sku_key(row)].add(normal(market))
        m = by_market[market]
        m['ofertas'] += 1
        m['cidades'].add(key)
        m['mais_recente'] = max(m['mais_recente'], row['atualizado'])
        datas[row['atualizado']] += 1
    comparable_by_city = {
        city: sum(len(markets) >= 2 for markets in skus.values())
        for city, skus in by_city_sku.items()
    }
    historico = {}
    try:
        previous = json.loads((base / 'saude_operacional.json').read_text(encoding='utf-8'))
        if isinstance(previous, dict):
            historico = previous
    except (OSError, ValueError, TypeError):
        pass
    old_count = historico.get('ofertas_validas')
    # Queda de cobertura é um aviso, não prova de defeito no robô.
    queda = None
    if isinstance(old_count, int) and old_count > 0:
        queda = round((old_count - len(validas)) / old_count * 100, 1)
    avisos = []
    if not validas:
        avisos.append('Nenhuma oferta recente validada nesta execução. Não divulgar preços como atuais.')
    if queda is not None and queda >= 35:
        avisos.append(f'Cobertura caiu {queda:g}% em relação ao relatório anterior; confira fontes e disponibilidade.')
    if conflitantes:
        avisos.append(f'{len(conflitantes)} URL(s) com dados contraditórios foram retiradas deste relatório.')
    if len(by_market) < 2 and validas:
        avisos.append('Apenas uma rede com ofertas recentes: comparações entre mercados indisponíveis.')
    if sum(comparable_by_city.values()) == 0 and validas:
        avisos.append('Nenhum produto comparável entre redes na mesma cidade nesta amostra.')
    estado = 'sem_ofertas' if not validas else 'atencao' if avisos else 'operacional'
    output = {
        'schema': 1,
        'gerado_em_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'data_referencia': hoje.isoformat(),
        'estado': estado,
        'ofertas_lidas': len(originais),
        'ofertas_validas': len(validas),
        'ofertas_rejeitadas': sum(rejeicoes.values()),
        'motivos_rejeicao': dict(rejeicoes.most_common()),
        'produtos_distintos': len({sku_key(r) for r in validas}),
        'redes_ativas': len(by_market),
        'cidades_com_oferta': len(by_city_sku),
        'produtos_comparaveis_mesma_cidade': sum(comparable_by_city.values()),
        'comparacoes_por_cidade': dict(sorted(comparable_by_city.items())),
        'ofertas_por_data': dict(sorted(datas.items())),
        'redes': [
            {'nome': name, 'ofertas': obj['ofertas'], 'cidades': len(obj['cidades']),
             'preco_mais_recente': obj['mais_recente']}
            for name, obj in sorted(by_market.items(), key=lambda pair: (-pair[1]['ofertas'], pair[0]))
        ],
        'queda_vs_anterior_percentual': queda,
        'avisos': avisos,
        'nota': 'Mede somente cobertura de dados públicos validados. Não mede visitantes, cliques de outros usuários, faturamento, estoque nem autorização comercial de uso.'
    }
    (base / 'saude_operacional.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as f:
            f.write('## Mercado em Conta — saúde da coleta\n\n')
            f.write(f"- Estado: **{estado}**\n- Ofertas válidas: **{len(validas)}**\n")
            f.write(f"- Redes: **{len(by_market)}**\n- Comparáveis na mesma cidade: **{sum(comparable_by_city.values())}**\n")
            f.write(f"- Rejeições: **{sum(rejeicoes.values())}**\n")
            for aviso in avisos:
                f.write(f'- ⚠️ {aviso}\n')
    for aviso in avisos:
        print('AVISO DE QUALIDADE:', aviso)
    print(f'SAÚDE: {estado} · {len(validas)} ofertas · {len(by_market)} redes · {sum(comparable_by_city.values())} comparações locais')
    return output


if __name__ == '__main__':
    montar()
