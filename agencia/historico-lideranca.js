#!/usr/bin/env node
// Exibição por hora de parede: eventos de processos diferentes não possuem ordem total causal.
const fs = require('node:fs');
const path = require('node:path');

const pasta = process.argv[2] || process.env.PASTA_DADOS || path.join(__dirname, 'data');
try {
  const eventos = fs.readdirSync(pasta).filter(nome => /^eventos-.*\.jsonl$/.test(nome))
    .flatMap(nome => fs.readFileSync(path.join(pasta, nome), 'utf8').split(/\r?\n/)
      .filter(Boolean).map((linha, indice) => {
        try { return JSON.parse(linha); }
        catch { throw new Error(`${nome}:${indice + 1}: JSON inválido`); }
      }))
    .filter(e => ['BULLY_ELEICAO_INICIADA', 'BULLY_ELEICAO_RECEBIDA',
      'BULLY_LIDER_ELEITA', 'BULLY_LIDER_ATUALIZADA', 'BULLY_LIDER_INDISPONIVEL'].includes(e.tipo))
    .sort((a, b) => String(a.horaParede).localeCompare(String(b.horaParede)) ||
      String(a.agencia).localeCompare(String(b.agencia)) || a.sequencia - b.sequencia);
  console.log('Histórico de liderança (hora de parede; não estabelece causalidade entre agências)');
  for (const e of eventos) {
    const detalhes = e.detalhes || {};
    const campos = ['liderId', 'origemId', 'motivo']
      .filter(campo => detalhes[campo] !== undefined && detalhes[campo] !== null)
      .map(campo => `${campo}=${detalhes[campo]}`).join(' ');
    console.log(`${e.horaParede} ${e.agencia} sessão=${e.sessaoProcesso} seq=${e.sequencia} ${e.tipo}${campos ? ' ' + campos : ''} vetor=${JSON.stringify(e.timestampVetorial)}`);
  }
  if (!eventos.length) console.log('Nenhuma mudança de liderança registrada.');
} catch (e) {
  console.error(`Não foi possível ler o histórico: ${e.message}`);
  process.exitCode = 1;
}
