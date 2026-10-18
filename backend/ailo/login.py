"""Login no iFood pelo terminal: ``uv run python -m ailo.login`` (em backend/).

Alternativa ao botão "Conectar iFood" da interface. Mostra a URL de login,
espera o retorno do navegador e salva os tokens em ``.data/``. Use quando a
Redirect URL do agente aponta para outra porta (ex.: http://localhost:8080/callback).
"""

from __future__ import annotations

import sys
import time

from .errors import AppError
from .ifood import oauth

POLL_INTERVAL_SECONDS = 1
TIMEOUT_SECONDS = 10 * 60


def main() -> int:
    if oauth.handles_callback_in_app():
        print("A Redirect URL aponta para o servidor do Ailo. Rode `npm run dev` e use o botão 'Conectar iFood'.")
        return 1

    oauth.logout()
    try:
        url = oauth.start_login()
    except AppError as error:
        print(error.message)
        return 1

    print("Abra esta URL no navegador e entre com a conta de teste (o OTP aparece no MCP Portal):\n")
    print(url)
    print("\nAguardando o login…")

    started = time.time()
    while not oauth.has_stored_login():
        if time.time() - started > TIMEOUT_SECONDS:
            print("Tempo esgotado. Rode o comando de novo.")
            return 1
        time.sleep(POLL_INTERVAL_SECONDS)

    print("Conta do iFood conectada! Agora rode `npm run dev` na raiz do projeto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
