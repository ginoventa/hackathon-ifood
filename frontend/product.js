import { products, formatPrice, readBag } from './catalog.js';

const productId = new URLSearchParams(window.location.search).get('id') || 'burger';
const product = products.find((item) => item.id === productId);
const form = document.querySelector('#product-form');
let quantity = 1;

function selectedExtras() {
  if (product.category !== 'Hambúrgueres') {
    return [];
  }

  return Array.from(form.querySelectorAll('input[name="extras"]:checked'));
}

function unitPrice() {
  return product.price + selectedExtras().reduce((total, input) => total + Number(input.value), 0);
}

function updateTotal() {
  document.querySelector('#quantity').textContent = quantity;
  document.querySelector('#item-total').textContent = formatPrice(unitPrice() * quantity);
  document.querySelector('#decrease').disabled = quantity <= 1;
  document.querySelector('#increase').disabled = quantity >= 20;
}

function initializeProduct() {
  document.title = `${product.name} • Burguer do Bairro`;
  document.querySelector('#product-name').textContent = product.name;
  document.querySelector('#product-description').textContent = product.description;

  if (product.dietaryLabel) {
    document.querySelector('#dietary-badge').textContent = product.dietaryLabel;
    document.querySelector('#dietary-badge').hidden = false;
  }

  document.querySelector('#product-price').textContent = formatPrice(product.price);
  document.querySelector('#product-image').src = product.image;
  document.querySelector('#product-image').alt = product.name;
  document.querySelector('#extras-group').hidden = product.category !== 'Hambúrgueres';

  if (product.originalPrice) {
    document.querySelector('#original-price').hidden = false;
    document.querySelector('#original-price').textContent = formatPrice(product.originalPrice);
  }

  document.querySelector('#decrease').addEventListener('click', () => {
    quantity = Math.max(1, quantity - 1);
    updateTotal();
  });
  document.querySelector('#increase').addEventListener('click', () => {
    quantity = Math.min(20, quantity + 1);
    updateTotal();
  });
  form.addEventListener('change', updateTotal);
  document.querySelector('#product-notes').addEventListener('input', (event) => {
    document.querySelector('#notes-count').textContent = `${event.target.value.length}/200`;
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const bag = readBag();
    bag.push({
      productId: product.id,
      name: product.name,
      quantity,
      unitPrice: unitPrice(),
      extras: selectedExtras().map((input) => input.dataset.label),
      notes: document.querySelector('#product-notes').value.trim(),
    });

    try {
      localStorage.setItem('ailo-bag', JSON.stringify(bag));
      window.location.href = './loja.html?sacola=1';
    } catch {
      const feedback = document.querySelector('#product-feedback');
      feedback.textContent = 'Não foi possível salvar a sacola. Verifique se o armazenamento do navegador está disponível.';
      feedback.hidden = false;
    }
  });

  updateTotal();
}

if (product) {
  initializeProduct();
} else {
  document.querySelector('#product-detail').hidden = true;
  document.querySelector('#missing-product').hidden = false;
}
