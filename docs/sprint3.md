# Sprint 3: liderança e sincronização offline

A Sprint 3 mantém o backend FastAPI, o RabbitMQ e o frontend web da Sprint 2.
O contrato de sincronização está descrito abaixo.

## Executar e demonstrar

Suba os serviços descritos no README principal com `docker compose up -d --build --wait`.
As agências se comunicam pelos nomes dos serviços dentro do Compose. Fora do
Compose, os endereços são configuráveis com `AGENCIA_0_URL`, `AGENCIA_1_URL`
e `AGENCIA_2_URL`. Configure as três URLs em cada processo quando necessário.

Consulte `GET /bully/lider` em cada agência. A eleição usa
`POST /bully/eleicao` e `POST /bully/coordenador`, com `origemId` ou `liderId`
e `vetorEnvio`. Parar a agência 2 deve provocar eleição da 1; ao voltar,
a 2 deve reassumir. Os parâmetros `BULLY_INTERVALO`, `BULLY_TIMEOUT` e
`BULLY_ESPERA_COORDENADOR` controlam os tempos em segundos. Para revisar os
eventos do Compose, execute `node agencia/historico-lideranca.js agencia/data/compose`.
Os logs são compartilhados com o host e preservados entre reinícios dos
containers; cada evento identifica a sessão da agência. Para processos iniciados
fora do Compose, informe a pasta configurada em `PASTA_DADOS` ou omita o
argumento para usar `agencia/data`.

O aplicativo e as instruções de preparação Android estão em [mobile/README.md](../mobile/README.md).
Uma conta precisa ser consultada online antes de realizar operações offline.

## Contrato de sincronização

`POST /sincronizacao` exige JWT. O corpo contém `operacaoId` (UUID), `contaId`,
`tipo` (`DEPOSITO`, `SAQUE` ou `TRANSFERENCIA`), `valor`, `vetorBase` e
`sessaoServidor`; para transferência, também `destinoId`. A consulta de conta
retorna `vetorVersao` e `sessaoServidor`. A resposta bem-sucedida contém a
conta atualizada e, para transferências, o estado de acompanhamento existente.

O servidor compara a versão da conta com a base do cliente. Uma versão
divergente ou outra sessão produz HTTP 409 com motivo e estado atual. Repetir
o mesmo UUID e pedido na mesma sessão não reaplica o débito. A confirmação de
publicação de uma transferência remota não garante crédito no destino; consulte
`GET /transferencias/{id}`. A fila local guarda operações e bloqueia as
seguintes da mesma conta quando ocorre conflito.

O contrato do roteiro também está disponível em `POST /contas/{id}/sincronizar`,
com `tipo`, `valor` e `vetorConhecido`. Essa rota compara o vetor da agência e
retorna HTTP 409 com `vetorAtual` e `contaAtual`; a rota usada pelo aplicativo
continua comparando a versão específica da conta e exige UUID e sessão.

## Limitações e validação pendente

- Com Postgres configurado, contas, versões, transferências e deduplicação
  persistem após reinício. Sem banco ficam em memória. A líder coordena a
  eleição, mas os dados de contas não são replicados para ela.
- O armazenamento pressupõe um processo por agência. Uma falha de commit
  interrompe as operações até reiniciar a agência e carregar o estado do banco.
  O JSONL não participa da transação do Postgres: uma falha de gravação no
  banco pode deixar no log um evento que não foi aplicado ao saldo.
- Com RabbitMQ e Postgres ativos, execute `cd agencia` e depois
  `uv run python -m unittest tests.test_integracao tests.test_integracao_sprint3 -v`.
  O teste da Sprint 3 verifica sincronização, transferência e failover reais.
- O app Flutter foi compilado e testado em Android físico para consulta de
  saldo, leitura do último saldo armazenado e failover da líder 2 → 1 → 2.
  Ainda faltam os ensaios reais de fila offline, reconexão e conflito visível.
- Adicionar os oito prints da seção 4.2 em `evidencias/sprint3/` e conferir
  as respostas de `RESPOSTAS.md` com os resultados da demonstração final.
