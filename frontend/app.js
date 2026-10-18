/**
 * Tela principal do Ailo: conversa com o agente.
 *
 * Responsável por: modos Restaurantes/Mercado, menu, endereço, ditado por voz,
 * envio de mensagens à API e exibição das respostas e cartões.
 */

import { api } from './api.js';
import { renderCard } from './chat-cards.js';
import { finalizeOrder, openCheckout } from './checkout.js';

const $ = selector => document.querySelector(selector);
const app = $('.app');
let mode = 'restaurants';
let toastTimer;
let isSending = false;
let status = null;
const conversationCards = new Map();

/** Textos e sugestões de cada modo, com pedidos gerais e restrições de exemplo. */
const config = {
  restaurants: {
    label: 'Restaurantes',
    icon: 'utensils',
    title: 'O que sua fome pede agora?',
    suggestions: ['Quero uma pizza', 'Sou celíaca e quero pizza', 'Lasanha sem leite (APLV)']
  },
  market: {
    label: 'Mercado',
    icon: 'cart',
    title: 'Bora cozinhar algo do seu jeito?',
    suggestions: ['Quero fazer pizza em casa', 'Lasanha sem leite e sem glúten', 'Bolo sem ovo']
  }
};

// ------------------------------------------------------------------ Modos

function setMode(next) {
  if (!config[next]) {
    return;
  }
  mode = next;
  const current = config[mode];
  app.dataset.mode = mode;
  $('#mode-label').textContent = current.label;
  $('#mode-caption').textContent = `Modo ${current.label}`;
  $('#welcome-title').textContent = current.title;
  $('#mode-icon').setAttribute('href', `./icons.svg#${current.icon}`);
  $('#caption-icon').setAttribute('href', `./icons.svg#${current.icon}`);
  $('#suggestions').replaceChildren(...current.suggestions.map((label, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `suggestion${index === 0 ? ' offer' : ''}`;
    if (index === 0) {
      button.append($('#offer-icon-template').content.cloneNode(true));
    }
    button.append(document.createTextNode(label));
    button.onclick = () => sendMessage(label);
    return button;
  }));
  $('#suggestions').scrollLeft = 0;
  closePopover();
  closeMenu();
  updateSend();
}

/** Pedidos para cozinhar em casa ("quero preparar em casa", "fazer em casa"). */
const HOME_COOKING_PATTERN = /\b(prepar\w*|fazer|fa[cç]o|cozinh\w*)\s[^.?!]*\bem casa\b|\breceita\b/i;

/** Passa para o modo Mercado quando a conversa vai para o preparo em casa. */
function switchToMarket() {
  if (mode === 'market') {
    return;
  }
  setMode('market');
  toast('Modo Mercado: vamos montar a lista de ingredientes.');
}

function closePopover() {
  $('#mode-popover').hidden = true;
  $('#mode-button').setAttribute('aria-expanded', 'false');
}

$('#mode-button').onclick = () => {
  const open = $('#mode-popover').hidden;
  $('#mode-popover').hidden = !open;
  $('#mode-button').setAttribute('aria-expanded', String(open));
};

document.querySelectorAll('[data-mode]').forEach(button => {
  if (button.tagName === 'BUTTON') {
    button.onclick = () => setMode(button.dataset.mode);
  }
});

document.addEventListener('click', event => {
  if (!event.target.closest('.mode-select-wrapper')) {
    closePopover();
  }
});

// ------------------------------------------------------------------- Menu

function closeMenu() {
  $('#drawer').hidden = true;
  $('#overlay').hidden = true;
  $('#menu-button').setAttribute('aria-expanded', 'false');
}

$('#menu-button').onclick = () => {
  $('#drawer').hidden = false;
  $('#overlay').hidden = false;
  $('#menu-button').setAttribute('aria-expanded', 'true');
  $('#close-menu').focus();
};

$('#close-menu').onclick = () => {
  closeMenu();
  $('#menu-button').focus();
};

$('#overlay').onclick = closeMenu;

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeMenu();
    closePopover();
  }
});

// ---------------------------------------------------------------- Endereço

/** Mostra o endereço no cabeçalho: apelido ("Casa"/"Trabalho") e só rua e número. */
function showAddress(address) {
  if (!address) {
    $('#address-value').textContent = 'Nenhum endereço salvo no iFood';
    return;
  }
  const streetAndNumber = address.formattedAddress.split(',').slice(0, 2).join(',');
  $('#address-value').textContent = address.alias ? `${address.alias} · ${streetAndNumber}` : streetAndNumber;
  $('#address-button').title = address.formattedAddress;
}

/** Abre o diálogo com os endereços salvos na conta do iFood. */
$('#address-button').onclick = async () => {
  const options = $('#address-options');
  const legend = options.querySelector('legend');
  options.replaceChildren(legend, Object.assign(document.createElement('p'), { className: 'dialog-hint', textContent: 'Carregando endereços…' }));
  $('#address-dialog').showModal();

  try {
    const { addresses } = await api.listAddresses();
    const current = $('#address-value').dataset.addressId;
    options.replaceChildren(legend, ...addresses.map(address => {
      const label = document.createElement('label');
      label.className = 'address-option';
      const input = Object.assign(document.createElement('input'), { type: 'radio', name: 'address', value: address.addressId });
      input.checked = address.addressId === current;
      const text = document.createElement('span');
      text.append(Object.assign(document.createElement('strong'), { textContent: address.alias ?? 'Endereço' }), address.formattedAddress);
      label.append(input, text);
      return label;
    }));
    if (addresses.length === 0) {
      options.append(Object.assign(document.createElement('p'), { className: 'dialog-hint', textContent: 'Nenhum endereço salvo na sua conta.' }));
    }
  } catch (error) {
    options.replaceChildren(legend, Object.assign(document.createElement('p'), { className: 'dialog-hint', textContent: error.message }));
  }
};

$('#address-dialog').addEventListener('close', async () => {
  const selected = $('#address-options input:checked')?.value;
  if ($('#address-dialog').returnValue !== 'save' || !selected) {
    return;
  }
  try {
    const session = await api.selectAddress(selected);
    $('#address-value').dataset.addressId = session.address.addressId;
    showAddress(session.address);
    toast('Endereço de entrega atualizado.');
  } catch (error) {
    toast(error.message);
  }
});

// -------------------------------------------------------------- Composição

function resizePrompt() {
  const prompt = $('#prompt');
  prompt.rows = 1;
  const lineHeight = Number.parseFloat(getComputedStyle(prompt).lineHeight);
  prompt.rows = Math.min(Math.ceil(prompt.scrollHeight / lineHeight), 3);
}

function updateSend() {
  const hasText = Boolean($('#prompt').value.trim());
  $('.wave').hidden = hasText;
  $('.send-icon').hidden = !hasText;
  $('#send-label').textContent = !hasText && mode === 'market' ? 'Fale' : '';
  $('#send-button').setAttribute('aria-label', hasText ? 'Enviar mensagem' : 'Falar com o Ailo');
  $('#send-button').disabled = isSending;
}

$('#prompt').addEventListener('input', () => {
  updateSend();
  resizePrompt();
});

$('#prompt').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $('#chat-form').requestSubmit();
  }
});

/** Coloca um texto no campo de mensagem para o usuário completar. */
function fillComposer(text) {
  $('#prompt').value = text;
  updateSend();
  resizePrompt();
  $('#prompt').focus();
  $('#prompt').setSelectionRange(text.length, text.length);
}

// ---------------------------------------------------------------- Conversa

function scrollToBottom() {
  $('#conversation').scrollTop = $('#conversation').scrollHeight;
}

function addMessage(text, role) {
  const element = document.createElement('div');
  element.className = `message ${role}`;
  element.textContent = text;
  $('#conversation').append(element);
  scrollToBottom();
  return element;
}

/** Ações disponíveis para os botões dos cartões. */
const cardActions = {
  send: (message, display, excludeItem) => sendMessage(message, display, excludeItem),
  consultRestaurant: (itemId, merchantId) => sendMessage('Quero consultar o restaurante', 'Consultar o restaurante', undefined, { itemId, merchantId }),
  fillComposer,
  openCheckout,
  finalizeOrder,
  toast,
  saveProfile: async inputs => {
    await api.saveProfile(inputs, true);
    toast('Perfil alimentar salvo neste dispositivo.');
  }
};

/** Atualiza a barra de restrições ativas acima do campo de mensagem. */
function showRestrictions(restrictions = []) {
  $('#restriction-bar').hidden = restrictions.length === 0;
  $('#restriction-summary').textContent = restrictions.map(restriction => restriction.label).join(' · ');
}

/** Entra no modo conversa (esconde boas-vindas e sugestões). */
function startChatLayout() {
  $('#welcome').hidden = true;
  $('#conversation').hidden = false;
  $('#suggestions').hidden = true;
  $('#demo-note').hidden = false;
  app.classList.add('chatting');
}

/** Atualiza cartões existentes em vez de repetir o mesmo bloco na conversa. */
function conversationCardKey({ type, data }) {
  if (type === 'restrictions' || type === 'recipe' || type === 'market') {
    return type;
  }
  if (type === 'analysis' || type === 'clarification') {
    return `${type}:${data.merchantId || data.merchantName}:${data.itemId || data.itemName}`;
  }
  if (type === 'cart') {
    return `${type}:${data.cartId}`;
  }
  if (type === 'options') {
    return `${type}:${JSON.stringify(data.items.map((item) => [item.merchantId, item.itemId]).sort())}`;
  }
  return `${type}:${JSON.stringify(data)}`;
}

/**
 * Envia uma mensagem ao agente.
 * @param {string} text Texto enviado ao backend (pode conter identificadores).
 * @param {string} [display] Texto mostrado na conversa, quando diferente do enviado.
 */
async function sendMessage(text, display = text, excludeItem, clarification) {
  if (!text.trim() || isSending) {
    return;
  }
  isSending = true;
  // Pedido de preparo em casa: o modo lá embaixo muda para Mercado antes de enviar.
  if (HOME_COOKING_PATTERN.test(text)) {
    switchToMarket();
  }
  startChatLayout();
  addMessage(display.trim(), 'user');
  $('#prompt').value = '';
  $('#prompt').rows = 1;
  updateSend();

  const pending = addMessage(mode === 'market' ? 'Pensando na receita e nos ingredientes…' : 'Investigando os cardápios para você…', 'assistant');
  pending.classList.add('pending');

  try {
    const response = await api.sendMessage(text.trim(), mode, excludeItem, clarification);
    pending.classList.remove('pending');
    pending.textContent = response.reply;
    // O agente entrou no fluxo de mercado (receita ou comparação de mercados).
    if (response.cards.some((cardData) => ['recipe', 'market'].includes(cardData.type))) {
      switchToMarket();
    }
    for (const cardData of response.cards) {
      const element = renderCard(cardData, cardActions);
      if (element) {
        const key = conversationCardKey(cardData);
        const previous = conversationCards.get(key);
        if (previous?.isConnected) {
          previous.replaceWith(element);
        } else {
          $('#conversation').append(element);
        }
        conversationCards.set(key, element);
      }
    }
    showRestrictions(response.restrictions);
  } catch (error) {
    pending.classList.remove('pending');
    pending.classList.add('error');
    pending.textContent = error.message;
    if (error.code === 'IFOOD_LOGIN_NECESSARIO') {
      showConnectBanner(true);
    }
  } finally {
    isSending = false;
    updateSend();
    scrollToBottom();
  }
}

$('#chat-form').onsubmit = event => {
  event.preventDefault();
  const text = $('#prompt').value;
  if (text.trim()) {
    sendMessage(text);
  } else startVoice();
};

$('#new-chat').onclick = async () => {
  $('#conversation').replaceChildren();
  conversationCards.clear();
  $('#conversation').hidden = true;
  $('#welcome').hidden = false;
  $('#suggestions').hidden = false;
  $('#demo-note').hidden = true;
  app.classList.remove('chatting');
  $('#prompt').value = '';
  updateSend();
  closeMenu();
  try {
    await api.resetSession();
  } catch (error) {
    toast(error.message);
  }
};

// ------------------------------------------------------------------ Avisos

function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => {
    $('#toast').hidden = true;
  }, 4500);
}

// -------------------------------------------------------------------- Voz

function startVoice() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    toast('A digitação por voz não está disponível neste navegador. Escreva seu pedido no campo acima.');
    $('#prompt').focus();
    return;
  }
  const recognition = new Recognition();
  recognition.lang = 'pt-BR';
  recognition.onstart = () => toast('Estou ouvindo… Diga o que você quer pedir.');
  recognition.onresult = event => {
    $('#prompt').value = event.results[0][0].transcript;
    updateSend();
    $('#toast').hidden = true;
    $('#prompt').focus();
  };
  recognition.onerror = () => toast('Não consegui acessar o microfone. Você pode digitar seu pedido.');
  try {
    recognition.start();
  } catch {
    toast('Não foi possível iniciar o microfone. Tente digitar seu pedido.');
  }
}

$('#mic-button').onclick = startVoice;

// ------------------------------------------------------- Conta do iFood

/** Mostra ou esconde o convite para conectar a conta do iFood. */
function showConnectBanner(visible) {
  $('#connect-banner').hidden = !visible;
}

/** Inicia o login OAuth do iFood numa nova aba. */
async function connectIfood() {
  try {
    const { authorizationUrl } = await api.loginIfood();
    window.open(authorizationUrl, '_blank', 'noopener');
    toast('Entre na sua conta do iFood na nova aba (na conta de teste, o código OTP aparece no MCP Portal). Depois volte aqui.');
  } catch (error) {
    toast(error.message);
  }
}

$('#connect-button').onclick = connectIfood;

$('#ifood-connection').onclick = async () => {
  if (!status?.ifoodConnected) {
    connectIfood();
    return;
  }
  try {
    await api.logoutIfood();
    toast('Conta do iFood desconectada.');
    await loadAccount();
  } catch (error) {
    toast(error.message);
  }
};

/** Carrega o status do servidor, a conta do iFood e as restrições salvas. */
async function loadAccount() {
  try {
    status = await api.status();
  } catch (error) {
    toast(error.message);
    return;
  }

  $('#ifood-connection-label').textContent = status.ifoodConnected ? 'Desconectar conta iFood' : 'Conectar conta iFood';
  if (status.problems.length) {
    toast(status.problems[0]);
  }

  if (!status.ifoodConnected) {
    // Sem as credenciais do agente, o login não funciona: avisa o que falta.
    $('#connect-text').textContent = status.credentialsConfigured
      ? 'Conecte sua conta do iFood para buscar opções perto de você.'
      : 'Configure IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET do seu agente no arquivo .env e reinicie o servidor.';
    $('#connect-button').hidden = !status.credentialsConfigured;
    showConnectBanner(true);
    $('#address-value').textContent = 'Conecte o iFood para ver seus endereços';
    return;
  }
  showConnectBanner(false);

  try {
    const session = await api.loadSession();
    const firstName = session.user?.fullName?.split(' ')[0];
    $('#greeting').textContent = firstName ? `Olá, ${firstName}` : 'Olá!';
    $('#drawer-greeting').textContent = firstName ? `Olá, ${firstName}` : 'Olá!';
    $('#address-value').dataset.addressId = session.address?.addressId ?? '';
    showAddress(session.address);
    showRestrictions(session.restrictions);
  } catch (error) {
    if (error.code === 'IFOOD_LOGIN_NECESSARIO') {
      showConnectBanner(true);
    }
    toast(error.message);
  }
}

// Ao voltar do login do iFood (em outra aba), recarrega a conta.
window.addEventListener('focus', () => {
  if (status && !status.ifoodConnected) {
    loadAccount();
  }
});

setMode('restaurants');
loadAccount();
