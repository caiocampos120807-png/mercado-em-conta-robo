#!/usr/bin/env python3
"""Evita perda por falha de coleta; preços vencidos vão ao arquivo, nunca ao comparador.

precos.csv: somente registros verificados nos últimos 2 dias.
catalogo_historico.csv: todos os registros previamente verificados, com a DATA ORIGINAL.
O arquivo histórico não é tabela de ofertas disponíveis para compra.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import coletar
from expandir_catalogo import read_csv, write_csv, valid_recent
from cesta_familia import report

BASE=Path(__file__).resolve().parent
FIELDS=coletar.FIELDS


def load_csv_text(text):
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):return []
    return [{k:str(row.get(k,'')).strip() for k in FIELDS} for row in reader if isinstance(row,dict)]


def baseline_from_git(base):
    result=subprocess.run(['git','show','HEAD:precos.csv'],cwd=base,text=True,capture_output=True,check=False)
    return load_csv_text(result.stdout) if result.returncode==0 else []


def valid_identity(row):
    try:
        p=urlsplit(str(row.get('link','')))
        if p.scheme!='https' or not p.hostname or p.username or p.password:return False
        price=coletar.br_price(row.get('preco'))
        if price is None:return False
        date.fromisoformat(str(row.get('atualizado','')))
        float(str(row.get('tamanho','')))
        return all(str(row.get(k,'')).strip() for k in FIELDS)
    except (ValueError,TypeError):return False


def merge(previous, latest, archived, today=None):
    today=today or date.today()
    history={}
    for row in [*archived,*previous,*latest]:
        if not valid_identity(row):continue
        url=row['link']
        old=history.get(url)
        if not old or row['atualizado'] >= old['atualizado']:
            history[url]=dict(row)
    current={}
    # Read previous before latest, so a newly verified value wins at equal date.
    for row in [*previous,*latest]:
        if not valid_identity(row) or not valid_recent(row,2,today):continue
        old=current.get(row['link'])
        if not old or row['atualizado']>=old['atualizado']:
            current[row['link']]=dict(row)
    return list(current.values()),list(history.values())


def run(base=BASE,previous=None,today=None):
    base=Path(base);today=today or date.today()
    previous=baseline_from_git(base) if previous is None else previous
    after=read_csv(base/'precos.csv')
    archive=read_csv(base/'catalogo_historico.csv')
    current,history=merge(previous,after,archive,today)
    write_csv(base/'precos.csv',current)
    write_csv(base/'catalogo_historico.csv',history)
    historic_keys={r['link'] for r in history}
    status={
        'atualizado_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'ofertas_ativas':len(current),
        'produtos_arquivados':len(historic_keys),
        'registrados_antes':len(previous),
        'novos_links_confirmados':len({r['link'] for r in current}-{r['link'] for r in previous}),
        'prioridades_familia_4':report(current),
        'aviso':'Catálogo histórico inclui preços vencidos; somente precos.csv contém ofertas recentes. Preços antigos não são atualizados artificialmente.'}
    (base/'cesta-status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PRESERVAÇÃO: {len(current)} preços recentes, {len(history)} links históricos; nenhum preço recebeu data artificial.')
    return status

if __name__=='__main__':run()
