class Cart {
  private items: number[] = [];

  add(price: number, qty?: number) {
    this.items.push(price * (qty ?? 1));
  }

  total() {
    return this.items.reduce((a, b) => a + b, 0);
  }
}

const cart = new Cart();
cart.add(5);
console.log([1, 2, 3].map(double), cart.total());

function double(n: number) {
  return n * 2;
}
