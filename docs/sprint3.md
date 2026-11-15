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

## Evidências da entrega

A seção 4.2 pede capturas reais em `evidencias/sprint3/`, com a data e hora
obtidas por `Get-Date` no PowerShell visíveis em cada print:

| Arquivo | Demonstração |
| --- | --- |
| `eleicao-inicial.png` | Convergência das três agências na subida |
| `failover.png` | Queda da líder e reeleição automática no backend |
| `historico-lideranca.png` | Execução do script com o histórico da demonstração |
| `app-lider-atual.png` | Líder atual no aplicativo Flutter |
| `app-failover.png` | Nova líder visível no aplicativo após a queda |
| `conflito-sincronizacao.png` | Resposta HTTP 409 do backend após mudança de vetor |
| `app-offline.png` | Operação pendente e saldo estimado no aplicativo offline |
| `app-sincronizacao.png` | Sincronização da operação após reconexão |

Registre também uma captura real da funcionalidade adicional (diagnóstico das
agências), por exemplo `funcionalidade-adicional.png`. Para os prints do app,
mantenha o telefone espelhado e o PowerShell com a data visíveis na mesma
captura. Gere os eventos no ambiente que será apresentado e confira os dados
antes de registrar as imagens. Os arquivos de teste e imagens de prévia não
substituem essas evidências.

Para reproduzir os quatro cenários de backend em um ambiente separado do
projeto principal, abra o PowerShell na raiz e execute, em ordem:

```powershell
.\scripts\evidencias-backend-sprint3.ps1 -Acao eleicao
.\scripts\evidencias-backend-sprint3.ps1 -Acao failover
.\scripts\evidencias-backend-sprint3.ps1 -Acao historico
.\scripts\evidencias-backend-sprint3.ps1 -Acao conflito
```

Após cada comando, capture a janela real com o `Get-Date` e o resultado visíveis
e salve com o nome indicado na tabela. O primeiro comando constrói e inicia o
projeto Docker `iceibank-evidencias` nas portas 4400–4402, 5438, 5682 e 15682;
ele possui volumes próprios. O failover religa a agência 2 ao terminar. O
conflito cria um usuário e uma conta de demonstração nesse ambiente, sem exibir
senha ou token. Não execute `docker compose down -v` se precisar preservar os
dados da demonstração. Os prints do aplicativo continuam sendo capturas
separadas no dispositivo Android.

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
  Novos eventos bancários são confirmados junto com o saldo no Postgres;
  o JSONL é uma cópia recuperável. Logs anteriores a essa mudança são importados
  como legado e não permitem verificar retroativamente se todos foram confirmados.
- Com RabbitMQ e Postgres ativos, execute `cd agencia` e depois
  `uv run python -m unittest tests.test_integracao tests.test_integracao_sprint3 -v`.
  O teste da Sprint 3 verifica sincronização, transferência e failover reais.
- Em Android físico foram validados login, movimentações, failover 2 → 1 → 2,
  fila e conflito 409 usando SQLite e backend reais. O teste de integração
  controlou a conectividade pelo cliente HTTP, sem desligar o Wi-Fi do aparelho;
  a persistência foi conferida reabrindo o SQLite e reconstruindo o widget,
  sem matar o processo Android. Esses dois cenários continuam pendentes em
  condições reais do sistema operacional.
- Os oito prints da seção 4.2 e a funcionalidade adicional estão em
  `evidencias/sprint3/`. O print da fila offline não mostra o saldo estimado;
  uma captura complementar é necessária para evidenciar a UI otimista.
