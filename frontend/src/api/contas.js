// MODEL - operações de conta (o "o que o sistema faz")
import { requisitar } from "./cliente.js";

export const consultarSaldo = (id) => requisitar(`/contas/${id}`);

export const depositar = (id, valor) =>
  requisitar(`/contas/${id}/depositar`, { metodo: "POST", corpo: { valor } });

export const sacar = (id, valor) =>
  requisitar(`/contas/${id}/sacar`, { metodo: "POST", corpo: { valor } });

export const criarConta = (id, nomeAluno, saldoInicial) =>
  requisitar("/contas", {
    metodo: "POST",
    corpo: { id, nomeAluno, saldoInicial },
  });

export const consultarHistorico = (id, opcoes = {}) =>
  requisitar(`/contas/${id}/historico?limite=50`, opcoes);

// Mesma regra do backend (id_conta % 3). Só para dar dicas na tela.
export const agenciaDaConta = (id) => ((Number(id) % 3) + 3) % 3;
