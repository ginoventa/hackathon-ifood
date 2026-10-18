/**
 * Erros da aplicação com código HTTP e mensagem amigável em português.
 * As rotas convertem estes erros em respostas JSON padronizadas.
 */

export class AppError extends Error {
  /**
   * @param {string} message Mensagem exibível ao usuário.
   * @param {object} [options]
   * @param {number} [options.status] Status HTTP.
   * @param {string} [options.code] Código estável para o frontend tratar.
   * @param {unknown} [options.cause] Erro original, para log.
   */
  constructor(message, { status = 500, code = 'ERRO_INTERNO', cause } = {}) {
    super(message, { cause });
    this.name = 'AppError';
    this.status = status;
    this.code = code;
  }
}

/** O usuário ainda não conectou a conta do iFood (ou o token expirou). */
export class IfoodAuthError extends AppError {
  constructor(message = 'Conecte sua conta do iFood para continuar.', cause) {
    super(message, { status: 401, code: 'IFOOD_LOGIN_NECESSARIO', cause });
    this.name = 'IfoodAuthError';
  }
}

/** Uma ferramenta do MCP do iFood respondeu com erro. */
export class IfoodToolError extends AppError {
  constructor(toolName, message, cause) {
    super(`O iFood recusou a operação ${toolName}: ${message}`, { status: 502, code: 'IFOOD_ERRO_FERRAMENTA', cause });
    this.name = 'IfoodToolError';
    this.toolName = toolName;
  }
}

/** Entrada inválida enviada pelo frontend. */
export class ValidationError extends AppError {
  constructor(message) {
    super(message, { status: 400, code: 'DADOS_INVALIDOS' });
    this.name = 'ValidationError';
  }
}
