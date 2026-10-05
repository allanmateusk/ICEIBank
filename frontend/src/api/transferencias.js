import { requisitar } from "./cliente.js";

export const transferir = (idOrigem, idDestino, valor, chave) =>
  requisitar("/transferencias", {
    metodo: "POST",
    corpo: { idOrigem, idDestino, valor },
    cabecalhos: { "Idempotency-Key": chave },
  });

export const consultarTransferencia = (id, opcoes = {}) =>
  requisitar(`/transferencias/${id}`, opcoes);

// Conserva o pedido sem resposta ao navegar, sair ou recarregar a mesma aba.
const chavePendente = (agencia) => `iceibank.transferencia-pendente.${agencia}`;
export function lerPedidoPendente(agencia) {
  try {
    return JSON.parse(sessionStorage.getItem(chavePendente(agencia))) || null;
  } catch {
    return null;
  }
}
export function guardarPedidoPendente(agencia, pedido) {
  // Se não for possível conservar a chave, não iniciar o débito.
  sessionStorage.setItem(chavePendente(agencia), JSON.stringify(pedido));
}
export function limparPedidoPendente(agencia, chave) {
  if (lerPedidoPendente(agencia)?.chave === chave)
    sessionStorage.removeItem(chavePendente(agencia));
}
