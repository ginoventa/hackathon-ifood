"""Login na conta do ChatGPT para usar a assinatura como LLM do agente.

Uso (na raiz do projeto)::

    npm run login-chatgpt            # abre o navegador (retorno em localhost:1455)
    npm run login-chatgpt -- --device  # sem navegador local: mostra um código para digitar

Usa os helpers EXPERIMENTAIS e NÃO OFICIAIS do ``langchain-openai``
(``login_chatgpt``). O token fica em ``backend/.data/chatgpt-auth.json``,
fora do git, separado do login do Codex CLI (``~/.codex``).
"""

from __future__ import annotations

import sys

from .config import config


def main() -> int:
    from langchain_openai.chatgpt_oauth import login_chatgpt, login_chatgpt_device

    config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    print("Entre com a sua conta do ChatGPT. O uso conta nos limites do seu plano.\n")
    try:
        if "--device" in sys.argv:
            login_chatgpt_device(store_path=config.chatgpt_token_path)
        else:
            login_chatgpt(store_path=config.chatgpt_token_path, open_browser=True)
    except (RuntimeError, TimeoutError, ValueError) as error:
        print(f"Não foi possível concluir o login: {error}")
        return 1

    print("\nChatGPT conectado! Reinicie o servidor (`npm run dev`) se ele estiver rodando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
