/**
 * Persistência simples em arquivos JSON dentro de `config.dataDir`.
 *
 * Suficiente para o MVP (um usuário por instalação). Os arquivos ficam fora
 * do git (ver .gitignore) e são gravados com permissão restrita (0600),
 * pois guardam tokens e dados de saúde.
 */

import { mkdir, readFile, rm, writeFile, rename } from 'node:fs/promises';
import { join } from 'node:path';

import { config } from '../config.js';

/** Caminho completo de um arquivo de dados. */
function dataPath(fileName) {
  return join(config.dataDir, fileName);
}

/**
 * Lê um arquivo JSON. Retorna `fallback` se ele não existir ou estiver inválido.
 * @template T
 * @param {string} fileName
 * @param {T} fallback
 * @returns {Promise<T>}
 */
export async function readJson(fileName, fallback) {
  try {
    return JSON.parse(await readFile(dataPath(fileName), 'utf8'));
  } catch (error) {
    if (error.code !== 'ENOENT') {
      console.warn(`[dados] Não foi possível ler ${fileName}:`, error.message);
    }
    return fallback;
  }
}

/**
 * Grava um objeto como JSON de forma atômica (arquivo temporário + rename),
 * para não corromper o arquivo se o processo for interrompido.
 */
export async function writeJson(fileName, value) {
  await mkdir(config.dataDir, { recursive: true, mode: 0o700 });
  const target = dataPath(fileName);
  const temporary = `${target}.${process.pid}.tmp`;
  await writeFile(temporary, JSON.stringify(value, null, 2), { mode: 0o600 });
  await rename(temporary, target);
}

/** Remove um arquivo de dados, se existir. */
export async function removeJson(fileName) {
  await rm(dataPath(fileName), { force: true });
}
