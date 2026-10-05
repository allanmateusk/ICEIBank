import { requisitar } from "./cliente.js";

export const transferir = (idOrigem, idDestino, valor, chave) =>
  requisitar("/transferencias", {
    metodo: "POST",
    corpo: { idOrigem, idDestino, valor },
    cabecalhos: { "Idempotency-Key": chave },
  });

export const consultarTransferencia = (id, opcoes = {}) =>
  requisitar(`/transferencias/${id}`, opcoes);
