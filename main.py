import argparse
import hashlib
import math
import os
import time
from multiprocessing import Event, Process, Queue

def fmt_seconds(seconds: float) -> str:
    if not math.isfinite(seconds):
        return "infinito"
    if seconds < 60:
        return f"{seconds:.2f} s"
    if seconds < 3600:
        return f"{seconds / 60:.2f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.2f} h"
    return f"{seconds / 86400:.2f} dias"


def brute_force_serial(hash_alvo: str, n_digitos: int):
    hash_bytes = bytes.fromhex(hash_alvo)
    inicio = time.perf_counter()
    total = 10 ** n_digitos

    for tentativa in range(total):
        senha = f"{tentativa:0{n_digitos}d}".encode("ascii")
        if hashlib.md5(senha).digest() == hash_bytes:
            tempo_total = time.perf_counter() - inicio
            return senha.decode("ascii"), tempo_total, tentativa + 1

    tempo_total = time.perf_counter() - inicio
    return None, tempo_total, total


def estimar_tempo_serial(n_digitos: int, amostras: int = 200_000):
    inicio = time.perf_counter()

    for i in range(amostras):
        senha = f"{i % (10 ** n_digitos):0{n_digitos}d}".encode("ascii")
        hashlib.md5(senha).digest()

    duracao = time.perf_counter() - inicio
    hash_por_segundo = amostras / duracao if duracao > 0 else float("inf")
    total = 10 ** n_digitos
    tempo_estimado = total / hash_por_segundo if hash_por_segundo > 0 else float("inf")
    return tempo_estimado, hash_por_segundo


def worker(
    hash_bytes: bytes,
    n_digitos: int,
    inicio_faixa: int,
    fim_faixa: int,
    encontrado: Event,
    resultado_queue: Queue,
):
    for tentativa in range(inicio_faixa, fim_faixa):
        if tentativa % 4096 == 0 and encontrado.is_set():
            return

        senha = f"{tentativa:0{n_digitos}d}".encode("ascii")
        if hashlib.md5(senha).digest() == hash_bytes:
            encontrado.set()
            resultado_queue.put(senha.decode("ascii"))
            return

def brute_force_parallel(hash_alvo: str, n_digitos: int, workers: int):
    hash_bytes = bytes.fromhex(hash_alvo)
    total = 10 ** n_digitos
    if workers < 1:
        workers = 1
    if workers > total:
        workers = total

    inicio = time.perf_counter()
    resultado_queue = Queue()
    encontrado = Event()

    base = total // workers
    resto = total % workers
    blocos = []
    inicio_bloco = 0
    for i in range(workers):
        tamanho = base + (1 if i < resto else 0)
        fim_bloco = inicio_bloco + tamanho
        blocos.append((inicio_bloco, fim_bloco))
        inicio_bloco = fim_bloco

    procs = [
        Process(
            target=worker,
            args=(
                hash_bytes,
                n_digitos,
                inicio_faixa,
                fim_faixa,
                encontrado,
                resultado_queue,
            ),
        )
        for inicio_faixa, fim_faixa in blocos
        if fim_faixa > inicio_faixa
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()

    tempo_total = time.perf_counter() - inicio
    senha = resultado_queue.get() if not resultado_queue.empty() else None
    return senha, tempo_total, len(procs)


def parse_workers(raw: str):
    itens = [x.strip() for x in raw.split(",") if x.strip()]
    workers = []
    for item in itens:
        valor = int(item)
        if valor > 0:
            workers.append(valor)
    return workers or [12, 8, 4, 2]


def main():
    parser = argparse.ArgumentParser(
        description="Brute force MD5 para senha numérica de 9 dígitos (serial e paralelo)."
    )
    parser.add_argument(
        "--hash",
        required=True,
        dest="hash_alvo",
        help="Hash MD5 alvo (32 hex).",
    )
    parser.add_argument(
        "--digits",
        type=int,
        default=9,
        help="Quantidade de dígitos da senha (padrão: 9).",
    )
    parser.add_argument(
        "--workers",
        default="12,8,4,2",
        help="Lista de workers separados por vírgula. Ex.: 12,8,4,2 (ordem de execução).",
    )
    parser.add_argument(
        "--serial-full",
        action="store_true",
        help="Executa brute force serial completo (pode demorar muito para 9 dígitos).",
    )

    args = parser.parse_args()
    workers_list = parse_workers(args.workers)

    print(f"Hash alvo: {args.hash_alvo}")
    print(f"Dígitos: {args.digits}")

    tempo_estimado, taxa = estimar_tempo_serial(args.digits)
    print("\n[Serial | T=1]")
    print(f"Taxa aproximada: {taxa:,.0f} hashes/s")
    print(f"Tempo estimado para percorrer 10^{args.digits}: {fmt_seconds(tempo_estimado)}")

    tempo_serial = None
    if args.serial_full:
        senha_serial, tempo_serial, tentativas = brute_force_serial(args.hash_alvo, args.digits)
        if senha_serial:
            print(f"Senha encontrada (serial): {senha_serial}")
        else:
            print("Senha não encontrada no espaço de busca.")
        print(f"Tempo serial real: {fmt_seconds(tempo_serial)}")
        print(f"Tentativas no serial: {tentativas:,}")
    else:
        print("Serial completo pulado (use --serial-full para executar).")

    tempos = {}
    for workers in workers_list:
        print(f"\n[Paralelo | workers={workers}]")
        senha_parallel, tempo_parallel, workers_usados = brute_force_parallel(
            args.hash_alvo, args.digits, workers
        )
        tempos[workers] = tempo_parallel

        print(f"Workers usados: {workers_usados}")
        if senha_parallel:
            print(f"Senha encontrada: {senha_parallel}")
        else:
            print("Senha não encontrada no espaço de busca.")
        print(f"Tempo: {fmt_seconds(tempo_parallel)}")

    if len(workers_list) >= 2:
        primeiro = workers_list[0]
        segundo = workers_list[1]
        t1 = tempos[primeiro]
        t2 = tempos[segundo]
        if t1 > 0 and t2 > 0:
            print(
                f"\nComparação: {primeiro} workers vs {segundo} workers = {t2 / t1:.2f}x no tempo"
            )

    if tempo_serial and workers_list:
        tmelhor = min(tempos.values())
        if tmelhor > 0:
            print(f"Speedup (serial vs melhor paralelo): {tempo_serial / tmelhor:.2f}x")


if __name__ == "__main__":
    main()
