"""Linha do tempo visual e relações causais (ordem de parede não é causal)."""
import argparse
import json
import os
from pathlib import Path
from src.services.relogio_vetorial import comparar_vetores, validar_vetor


def carregar_eventos(pasta: Path) -> list[dict]:
    eventos = []
    for arquivo in sorted(pasta.glob("eventos-*.jsonl")):
        with arquivo.open(encoding="utf-8") as f:
            eventos.extend(json.loads(linha) for linha in f if linha.strip())
    return sorted(eventos, key=lambda e: e["horaParede"])


def analisar(eventos: list[dict]) -> list[tuple[dict, dict]]:
    sessoes = {}
    for evento in eventos:
        if "timestampVetorial" not in evento:
            continue
        validar_vetor(evento["timestampVetorial"], 3)
        sessoes.setdefault(evento["agencia"], set()).add(evento.get("sessaoProcesso", "desconhecida"))
    if any(len(s) > 1 for s in sessoes.values()):
        raise ValueError("Reinicio detectado: nao compare vetores de sessoes diferentes. Use um experimento continuo em pasta separada.")
    novos = [e for e in eventos if "timestampVetorial" in e]
    return [(a, b) for i, a in enumerate(novos) for b in novos[i + 1:]
            if a["agencia"] != b["agencia"] and
            comparar_vetores(a["timestampVetorial"], b["timestampVetorial"]) == "CONCORRENTES"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pasta", type=Path, default=Path(os.environ.get("PASTA_DADOS", Path(__file__).parent / "data")))
    parser.add_argument("--limite-pares", type=int, default=50)
    args = parser.parse_args()
    if args.limite_pares < 1:
        parser.error("--limite-pares deve ser positivo")
    eventos = carregar_eventos(args.pasta)
    print("=== Linha do tempo por hora de parede (exibicao; nao define causalidade) ===")
    for e in eventos:
        vetor = e.get("timestampVetorial", "Lamport legado=" + str(e.get("timestampLamport")))
        print(f"{e['agencia']} vetor={vetor} {e['tipo']} {json.dumps(e['detalhes'], ensure_ascii=False)}")
    try:
        pares = analisar(eventos)
    except ValueError as erro:
        print(f"Analise causal indisponivel: {erro}")
        return 2
    print("\n=== Pares CONCORRENTES entre agencias diferentes ===")
    for a, b in pares[:args.limite_pares]:
        print(f"{a['agencia']} {a['tipo']} {a['timestampVetorial']} x {b['agencia']} {b['tipo']} {b['timestampVetorial']}")
    print(f"Total: {len(pares)} pares concorrentes; exibidos: {min(len(pares), args.limite_pares)}.")
    if not pares:
        print("Gere operacoes independentes em agencias distintas para observar concorrencia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
