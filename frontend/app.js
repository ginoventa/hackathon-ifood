const $ = selector => document.querySelector(selector);
const app = $('.app');
let mode = 'restaurants';
let replyTimer;
let toastTimer;
const config = {
  restaurants: {
    label: 'Restaurantes',
    icon: 'utensils',
    title: 'O que sua fome pede agora?',
    suggestions: ['50% off', 'Repetir último pedido', 'Sugestões para jantar', 'Quero algo saudável']
  },
  market: {
    label: 'Mercado',
    icon: 'cart',
    title: 'Bora de comprinhas da semana?',
    suggestions: []
  }
};
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
    button.className = `suggestion${index === 0 ? ' offer' : ''}`;
    if (index === 0) {
      button.append($('#offer-icon-template').content.cloneNode(true));
    }
    button.append(document.createTextNode(label));
    button.onclick = () => sendMessage(label);
    return button;
  }));
  closePopover();
  closeMenu();
  updateSend();
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
$('#address-button').onclick = () => $('#address-dialog').showModal();
$('#address-dialog').addEventListener('close', () => {
  if ($('#address-dialog').returnValue === 'save') {
    const value = $('#address-input').value.trim();
    if (value) {
      $('#address-value').textContent = value;
    }
  }
});
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
function addMessage(text, role) {
  const element = document.createElement('div');
  element.className = `message ${role}`;
  element.textContent = text;
  $('#conversation').append(element);
  $('#conversation').scrollTop = $('#conversation').scrollHeight;
  return element;
}
function sendMessage(text) {
  if (!text.trim()) {
    return;
  }
  clearTimeout(replyTimer);
  document.querySelector('.message.pending')?.remove();
  $('#welcome').hidden = true;
  $('#conversation').hidden = false;
  $('#suggestions').hidden = true;
  $('#demo-note').hidden = false;
  app.classList.add('chatting');
  addMessage(text.trim(), 'user');
  $('#prompt').value = '';
  $('#prompt').rows = 1;
  updateSend();
  const pending = addMessage('Pensando no que combina com você…', 'assistant');
  pending.classList.add('pending');
  const selectedMode = mode;
  replyTimer = setTimeout(() => {
    pending.classList.remove('pending');
    pending.textContent = getDemoResponse(text, selectedMode);
    $('#conversation').scrollTop = $('#conversation').scrollHeight;
  }, 850);
}
$('#chat-form').onsubmit = event => {
  event.preventDefault();
  const text = $('#prompt').value;
  if (text.trim()) {
    sendMessage(text);
  } else startVoice();
};
$('#new-chat').onclick = () => {
  clearTimeout(replyTimer);
  $('#conversation').replaceChildren();
  $('#conversation').hidden = true;
  $('#welcome').hidden = false;
  $('#suggestions').hidden = false;
  $('#demo-note').hidden = true;
  app.classList.remove('chatting');
  $('#prompt').value = '';
  updateSend();
  closeMenu();
};
function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => {
    $('#toast').hidden = true;
  }, 4500);
}
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
setMode('restaurants');
function getDemoResponse(text, selectedMode) {
  if (selectedMode === 'market') {
    return 'Bora montar sua lista! 🛒\n\nPodemos começar com frutas, verduras, leite, ovos e os básicos da despensa. Para quantas pessoas e quantos dias você quer comprar?\n\nEsta é uma conversa demonstrativa. Os produtos e preços ainda não estão conectados a um mercado.';
  }
  if (/50%|off|promo/i.test(text)) {
    return 'Uma boa oferta deixa tudo mais gostoso! 💗\n\nVocê está com vontade de pizza, hambúrguer ou comida brasileira? Me conta também quanto quer gastar.\n\nEste protótipo ainda não consulta cupons ou ofertas reais.';
  }
  if (/repetir|último/i.test(text)) {
    return 'Vamos de favorito? 💗\n\nAinda não tenho acesso ao seu histórico de pedidos neste protótipo. Me conta qual foi o prato e eu te ajudo a pensar no pedido!';
  }
  return 'Vamos encontrar algo gostoso! 💗\n\nVocê prefere uma refeição completa, um lanche ou algo mais leve? Me conta sua preferência e quanto quer gastar.\n\nEsta é uma conversa demonstrativa, ainda sem conexão com restaurantes ou uma IA.';
}
