// Helpers de conversão de texto digitado -> número.

// Aceita vírgula decimal (pt-BR) e ponto de milhar:
//   "100,00"    -> 100
//   "1.234,56"  -> 1234.56
//   "50.5"      -> 50.5
//   ""          -> NaN
export function paraNumero(texto) {
  if (typeof texto === "number") return Number.isFinite(texto) ? texto : NaN;
  let s = String(texto).trim();
  if (s === "") return NaN;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const numero = Number(s);
  return Number.isFinite(numero) ? numero : NaN;
}

// Número de conta: inteiro >= 0. Retorna NaN se não for.
export function paraInteiroConta(texto) {
  const s = String(texto).trim();
  if (!/^\d+$/.test(s)) return NaN;
  const numero = Number(s);
  return Number.isSafeInteger(numero) ? numero : NaN;
}

export const moeda = (valor) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    valor,
  );
