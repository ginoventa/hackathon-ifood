/**
 * Página de perfil alimentar.
 *
 * Lista as restrições do catálogo agrupadas por tipo, permite adicionar
 * restrições personalizadas e salva o perfil SOMENTE com consentimento.
 */

import { api } from './api.js';
import { el, RESTRICTION_TYPE_LABELS } from './format.js';

const $ = (selector) => document.querySelector(selector);

/** Ordem e descrição dos grupos exibidos. */
const GROUPS = [
  { type: 'ALERGIA', hint: 'Reação do sistema imunológico. Análise com rigor máximo, incluindo contato cruzado.' },
  { type: 'DOENCA_CELIACA', hint: 'Mesmo traços de glúten importam. Análise com rigor máximo.' },
  { type: 'INTOLERANCIA', hint: 'Dificuldade de digerir uma substância.' },
  { type: 'RELIGIOSA', hint: 'Regras da sua fé, como halal, kosher ou não comer carne de porco. Certificações contam como evidência.' },
  { type: 'PREFERENCIA', hint: 'Escolhas alimentares, como vegetarianismo.' },
];

/** Restrições personalizadas ainda não salvas. */
let customRestrictions = [];
let toastTimer;

function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => {
    $('#toast').hidden = true;
  }, 4000);
}

function showError(message) {
  $('#profile-error').textContent = message;
  $('#profile-error').hidden = !message;
}

/** Desenha os grupos de restrições do catálogo como caixas de seleção. */
function renderCatalog(catalog, selectedIds) {
  const groups = GROUPS.map((group) => {
    const options = catalog.filter((restriction) => restriction.type === group.type);
    if (options.length === 0) {
      return null;
    }
    return el('fieldset', { className: 'profile-group' }, [
      el('legend', {}, [RESTRICTION_TYPE_LABELS[group.type], el('span', { text: group.hint })]),
      el('div', { className: 'profile-options' }, options.map((restriction) => {
        const input = el('input', { attrs: { type: 'checkbox', name: 'restriction', value: restriction.id } });
        input.checked = selectedIds.has(restriction.id);
        return el('label', { className: 'profile-option' }, [input, el('span', { text: restriction.label })]);
      })),
    ]);
  });
  $('#restriction-groups').replaceChildren(...groups.filter(Boolean));
}

/** Desenha a lista de restrições personalizadas. */
function renderCustomList() {
  $('#custom-list').replaceChildren(...customRestrictions.map((restriction, index) => {
    const remove = el('button', { className: 'card-button link', text: 'Remover', attrs: { type: 'button' } });
    remove.addEventListener('click', () => {
      customRestrictions.splice(index, 1);
      renderCustomList();
    });
    return el('li', {}, [
      el('span', {}, [
        el('strong', { text: restriction.nome }),
        el('small', { text: `${RESTRICTION_TYPE_LABELS[restriction.tipo]} · ${restriction.termos.join(', ')}` }),
      ]),
      remove,
    ]);
  }));
}

$('#add-custom').addEventListener('click', () => {
  const nome = $('#custom-name').value.trim();
  const termos = $('#custom-terms').value.split(',').map((term) => term.trim()).filter(Boolean);
  if (!nome || termos.length === 0) {
    toast('Informe o nome e pelo menos uma palavra que indique a substância.');
    return;
  }
  customRestrictions.push({ id: 'personalizada', nome, tipo: $('#custom-type').value, termos });
  $('#custom-name').value = '';
  $('#custom-terms').value = '';
  renderCustomList();
});

$('#profile-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  showError('');

  if (!$('#profile-consent').checked) {
    showError('Para salvar, marque a autorização de armazenamento.');
    return;
  }

  const selected = [...document.querySelectorAll('input[name="restriction"]:checked')].map((input) => ({ id: input.value }));
  try {
    await api.saveProfile([...selected, ...customRestrictions], true);
    toast('Perfil salvo! As próximas conversas já vão considerar estas restrições.');
  } catch (error) {
    showError(error.message);
  }
});

$('#delete-profile').addEventListener('click', async () => {
  if (!window.confirm('Apagar seu perfil alimentar deste dispositivo?')) {
    return;
  }
  try {
    await api.deleteProfile();
    document.querySelectorAll('input[name="restriction"]').forEach((input) => {
      input.checked = false;
    });
    customRestrictions = [];
    renderCustomList();
    $('#profile-consent').checked = false;
    toast('Perfil apagado.');
  } catch (error) {
    showError(error.message);
  }
});

/** Carrega o catálogo e o perfil salvo. */
async function initialize() {
  try {
    const [{ restrictions: catalog }, profile] = await Promise.all([api.restrictionCatalog(), api.getProfile()]);
    const selectedIds = new Set(profile.restrictions.map((restriction) => restriction.id));
    customRestrictions = profile.restrictions.filter((restriction) => restriction.id === 'personalizada');
    renderCatalog(catalog, selectedIds);
    renderCustomList();
    $('#profile-consent').checked = Boolean(profile.consentAt);
  } catch (error) {
    $('#restriction-groups').replaceChildren(el('p', { className: 'checkout-error', text: error.message }));
  }
}

initialize();
