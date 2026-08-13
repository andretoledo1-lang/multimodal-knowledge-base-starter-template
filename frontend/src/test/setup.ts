import "@testing-library/jest-dom/vitest";

Object.defineProperty(Element.prototype, "scrollTo", {
  configurable: true,
  value: () => undefined,
});

const localValues = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    getItem: (key: string) => localValues.get(key) ?? null,
    setItem: (key: string, value: string) => localValues.set(key, value),
    removeItem: (key: string) => localValues.delete(key),
    clear: () => localValues.clear(),
  },
});
