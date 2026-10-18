import { products, formatPrice, readBag } from './catalog.js';

const search = document.querySelector('#menu-search');
const bagDialog = document.querySelector('#bag-dialog');

function renderProducts() {
  const query = search.value.trim().toLocaleLowerCase('pt-BR');
  let matches = 0;

  document.querySelectorAll('[data-category]').forEach((grid) => {
    grid.replaceChildren();

    const visibleProducts = products.filter((product) => (
      product.category === grid.dataset.category
      && `${product.name} ${product.description}`.toLocaleLowerCase('pt-BR').includes(query)
    ));

    grid.closest('section').hidden = visibleProducts.length === 0;
    matches += visibleProducts.length;

    visibleProducts.forEach((product) => {
      const card = document.querySelector('#product-card-template').content.cloneNode(true);
      card.querySelector('a').href = `./produto.html?id=${product.id}`;
      card.querySelector('h3').textContent = product.name;
      card.querySelector('p').textContent = product.description;

      if (product.dietaryLabel) {
        card.querySelector('.dietary-badge').textContent = product.dietaryLabel;
        card.querySelector('.dietary-badge').hidden = false;
      }
      card.querySelector('strong').textContent = formatPrice(product.price);
      card.querySelector('img').src = product.image;
      card.querySelector('img').alt = product.name;

      if (product.originalPrice) {
        card.querySelector('del').hidden = false;
        card.querySelector('del').textContent = formatPrice(product.originalPrice);
      }

      grid.append(card);
    });
  });

  document.querySelector('#search-empty').hidden = matches > 0;
}

function renderBag() {
  const bag = readBag();
  const container = document.querySelector('#bag-items');
  container.replaceChildren();

  const count = bag.reduce((total, item) => total + item.quantity, 0);
  const total = bag.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);

  document.querySelectorAll('.bag-count').forEach((element) => {
    element.textContent = count;
  });
  document.querySelector('#mobile-bag-total').textContent = formatPrice(total);
  document.querySelector('#mobile-bag-bar').hidden = count === 0;
  document.body.classList.toggle('has-bag', count > 0);
  document.querySelector('#bag-total').textContent = formatPrice(
    bag.reduce((total, item) => total + item.quantity * item.unitPrice, 0),
  );

  if (bag.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Sua sacola está esperando algo gostoso. Explore o cardápio!';
    container.append(empty);
  }

  bag.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'bag-item';
    const description = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = `${item.quantity}× ${item.name}`;
    const details = document.createElement('p');
    details.textContent = [...(item.extras || []), item.notes].filter(Boolean).join(' · ');
    const price = document.createElement('span');
    price.textContent = formatPrice(item.quantity * item.unitPrice);
    description.append(name, details);
    row.append(description, price);
    container.append(row);
  });

  document.querySelector('#clear-bag').disabled = bag.length === 0;
}

search.addEventListener('input', renderProducts);
document.querySelectorAll('.bag-trigger').forEach((button) => {
  button.addEventListener('click', () => {
    renderBag();
    bagDialog.showModal();
  });
});

document.querySelector('#mobile-search').addEventListener('click', () => {
  search.scrollIntoView({ block: 'center' });
  search.focus({ preventScroll: true });
});

const categoryLinks = document.querySelectorAll('.categories a');

categoryLinks.forEach((link) => {
  link.addEventListener('click', () => {
    categoryLinks.forEach((item) => {
      item.classList.toggle('active', item === link);
      item.removeAttribute('aria-current');
    });
    link.setAttribute('aria-current', 'location');
  });
});
document.querySelector('#close-bag').addEventListener('click', () => {
  bagDialog.close();
});
document.querySelector('#clear-bag').addEventListener('click', () => {
  try {
    localStorage.removeItem('ailo-bag');
    renderBag();
  } catch {
    document.querySelector('#bag-items').textContent = 'Não foi possível atualizar a sacola neste navegador.';
  }
});
document.querySelector('#favorite').addEventListener('click', (event) => {
  const button = event.currentTarget;
  const selected = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(selected));
  button.textContent = selected ? '♥' : '♡';
});
window.addEventListener('pageshow', renderBag);
renderProducts();
renderBag();

if (new URLSearchParams(window.location.search).get('sacola') === '1') {
  bagDialog.showModal();
  window.history.replaceState(null, '', './loja.html');
}
