export const products = [
  {
    id: 'burger',
    name: 'Burger da casa',
    description: 'Pão brioche, hambúrguer de 180 g, cheddar cremoso, bacon crocante e maionese da casa.',
    price: 29.9,
    originalPrice: 36.9,
    category: 'Hambúrgueres',
    image: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=1000&q=85',
  },
  {
    id: 'double',
    name: 'Duplo cheddar',
    description: 'Dois hambúrgueres de 120 g, cheddar em dobro e cebola caramelizada no pão brioche.',
    price: 36.9,
    category: 'Hambúrgueres',
    image: 'https://images.unsplash.com/photo-1550547660-d9450f859349?auto=format&fit=crop&w=1000&q=85',
  },
  {
    id: 'fries',
    name: 'Batata frita crocante',
    description: 'Porção de batatas douradinhas, com sal na medida e maionese da casa. Serve 2 pessoas.',
    price: 19.9,
    category: 'Acompanhamentos',
    image: 'https://images.unsplash.com/photo-1573080496219-bb080dd4f877?auto=format&fit=crop&w=1000&q=85',
  },
  {
    id: 'vegan',
    name: 'Burger vegetariano de grão-de-bico',
    description: 'Pão de fermentação natural sem ingredientes de origem animal, burger de grão-de-bico, alface, tomate e maionese vegetal.',
    price: 32.9,
    category: 'Opções especiais',
    image: 'https://images.unsplash.com/photo-1520072959219-c595dc870360?auto=format&fit=crop&w=1000&q=85',
    dietary: ['vegetarian', 'vegan', 'lactose-free'],
    dietaryLabel: 'Sem lactose',
  },
  {
    id: 'gluten-free',
    name: 'Burger no pão de arroz',
    description: 'Pão de farinha de arroz, hambúrguer bovino de 180 g, alface, tomate e azeite. Sem queijo e sem molho lácteo na receita.',
    price: 34.9,
    category: 'Opções especiais',
    image: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=1000&q=85',
    dietary: ['gluten-free', 'lactose-free'],
    dietaryLabel: 'Sem glúten',
  },
];

export function formatPrice(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

export function readBag() {
  try {
    const items = JSON.parse(localStorage.getItem('ailo-bag') || '[]');

    if (!Array.isArray(items)) {
      return [];
    }

    return items.filter((item) => (
      typeof item.name === 'string'
      && Number.isInteger(item.quantity)
      && item.quantity > 0
      && Number.isFinite(item.unitPrice)
      && item.unitPrice >= 0
    ));
  } catch {
    return [];
  }
}
