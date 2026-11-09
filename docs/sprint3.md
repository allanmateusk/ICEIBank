# Sprint 3: liderança e sincronização offline

Esta implementação parte da Sprint 2 e conserva o backend FastAPI, RabbitMQ e
frontend web. O enunciado completo das seções 2 a 10 não estava disponível;
o contrato abaixo é provisório e deve ser conferido com o roteiro da disciplina.

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
eventos, execute `node agencia/historico-lideranca.js`; para outra pasta de
logs, informe o caminho como primeiro argumento.

O aplicativo e as instruções de preparação Android estão em [mobile/README.md](../mobile/README.md).
Uma conta precisa ser consultada online antes de realizar operações offline.

## Contrato provisório de sincronização

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

## Limitações e validação pendente

- Contas, versões e chaves de deduplicação estão em memória e são perdidas ao
  reiniciar a agência; uma fila antiga exige reconciliação. A líder coordena a
  eleição, mas os dados de contas não são replicados para ela.
- Com RabbitMQ e Postgres ativos, execute `cd agencia` e depois
  `uv run python -m unittest tests.test_integracao tests.test_integracao_sprint3 -v`.
  O teste da Sprint 3 verifica sincronização, transferência e failover reais.
- O app Flutter precisa ser compilado e testado em dispositivo/emulador,
  incluindo queda da líder, retomada da fila e conflito visível.
- Criar `evidencias/sprint3/` com os oito prints oficiais após obter a seção 4.2.
  Atualizar RESPOSTAS.md após obter as questões das seções 5.5, 6.4, 7.3,
  8.3, 9.6 e 10.3; não inventar enunciados ou resultados observados.
