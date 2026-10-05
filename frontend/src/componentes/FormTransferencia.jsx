import { useState } from "react";
import { agenciaDaConta } from "../api/contas.js";
import { moeda, paraInteiroConta, paraNumero } from "../util/numeros.js";

export default function FormTransferencia({
  aoTransferir,
  agenciaAtual,
  conta,
}) {
  const [origem, setOrigem] = useState(String(conta?.id ?? agenciaAtual));
  const [destino, setDestino] = useState("");
  const [valor, setValor] = useState("");
  const [erro, setErro] = useState("");
  const [pedido, setPedido] = useState(null);
  const [enviando, setEnviando] = useState(false);
  function editar(setter, value) {
    setter(value);
    setPedido(null);
    setErro("");
  }
  function revisar(e) {
    e.preventDefault();
    const idOrigem = paraInteiroConta(origem),
      idDestino = paraInteiroConta(destino),
      n = paraNumero(valor);
    if (Number.isNaN(idOrigem) || Number.isNaN(idDestino))
      return setErro("Informe números de conta válidos.");
    if (idOrigem === idDestino)
      return setErro("Origem e destino devem ser diferentes.");
    if (agenciaDaConta(idOrigem) !== agenciaAtual)
      return setErro(
        `A origem pertence à Agência ${agenciaDaConta(idOrigem)}. Troque a agência atual.`,
      );
    if (
      !Number.isFinite(n) ||
      n <= 0 ||
      Math.abs(n * 100 - Math.round(n * 100)) > 0.000001
    )
      return setErro("Informe um valor positivo com até duas casas decimais.");
    if (conta?.id === idOrigem && n > conta.saldo)
      return setErro("Saldo insuficiente.");
    setErro("");
    setPedido({ idOrigem, idDestino, valor: n, chave: crypto.randomUUID() });
  }
  async function enviar() {
    if (enviando) return;
    setEnviando(true);
    try {
      const r = await aoTransferir(
        pedido.idOrigem,
        pedido.idDestino,
        pedido.valor,
        pedido.chave,
      );
      if (r) {
        setPedido(null);
        setValor("");
      }
    } finally {
      setEnviando(false);
    }
  }
  return (
    <section className="cartao">
      <h2>Entre contas e agências</h2>
      <p className="muted">Revise os dados antes de enviar.</p>
      <form onSubmit={revisar} className="form-grid">
        <label>
          Conta de origem
          <input
            value={origem}
            onChange={(e) => editar(setOrigem, e.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label>
          Conta de destino
          <input
            value={destino}
            onChange={(e) => editar(setDestino, e.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label className="full">
          Valor (R$)
          <input
            value={valor}
            onChange={(e) => editar(setValor, e.target.value)}
            inputMode="decimal"
            placeholder="0,00"
            required
          />
        </label>
        {!pedido && <button className="full">Revisar transferência</button>}
      </form>
      {erro && (
        <p className="alerta" role="alert">
          {erro}
        </p>
      )}
      {pedido && (
        <div className="revisao">
          <h3>Confira sua transferência</h3>
          <p>
            <strong>{moeda(pedido.valor)}</strong> da conta {pedido.idOrigem}{" "}
            para a conta {pedido.idDestino}.
          </p>
          <p className="muted">
            Destino: Agência {agenciaDaConta(pedido.idDestino)} ·{" "}
            {agenciaDaConta(pedido.idDestino) === agenciaAtual
              ? "transferência local"
              : "crédito confirmado após processamento no destino"}
          </p>
          <div className="acoes">
            <button type="button" disabled={enviando} onClick={enviar}>
              {enviando ? "Enviando…" : "Confirmar envio"}
            </button>
            <button
              type="button"
              disabled={enviando}
              className="ghost"
              onClick={() => setPedido(null)}
            >
              Editar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
