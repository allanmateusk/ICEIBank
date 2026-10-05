import { useState } from "react";
import { agenciaDaConta } from "../api/contas.js";
import { moeda, paraInteiroConta, paraNumero } from "../util/numeros.js";
import {
  lerPedidoPendente,
  guardarPedidoPendente,
} from "../api/transferencias.js";

export default function FormTransferencia({
  aoTransferir,
  agenciaAtual,
  conta,
}) {
  const [inicial] = useState(() => lerPedidoPendente(agenciaAtual));
  const [origem, setOrigem] = useState(
    String(inicial?.idOrigem ?? conta?.id ?? agenciaAtual),
  );
  const [destino, setDestino] = useState(String(inicial?.idDestino ?? ""));
  const [valor, setValor] = useState(String(inicial?.valor ?? ""));
  const [erro, setErro] = useState("");
  const [pedido, setPedido] = useState(inicial);
  const [incerto, setIncerto] = useState(!!inicial);
  const [enviando, setEnviando] = useState(false);
  function editar(setter, value) {
    setter(value);
    setPedido(null);
    setErro("");
  }
  function revisar(e) {
    e.preventDefault();
    if (incerto) return;
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
      guardarPedidoPendente(agenciaAtual, pedido);
      setIncerto(true);
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
      if (!lerPedidoPendente(agenciaAtual)) {
        setIncerto(false);
        setPedido(null);
      }
    } catch {
      setErro(
        "Não foi possível guardar o pedido nesta aba. Nenhum novo envio foi iniciado.",
      );
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
            disabled={incerto}
            value={origem}
            onChange={(e) => editar(setOrigem, e.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label>
          Conta de destino
          <input
            disabled={incerto}
            value={destino}
            onChange={(e) => editar(setDestino, e.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label className="full">
          Valor (R$)
          <input
            disabled={incerto}
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
          {incerto && (
            <p role="status">
              O resultado deste pedido ainda precisa ser recuperado. Reutilize o
              mesmo pedido antes de iniciar outra transferência.
            </p>
          )}
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
              {enviando
                ? "Enviando…"
                : incerto
                  ? "Recuperar resultado"
                  : "Confirmar envio"}
            </button>
            <button
              type="button"
              disabled={enviando || incerto}
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
