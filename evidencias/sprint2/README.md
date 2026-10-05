# Evidências da sprint2

Geradas por `npm run test:e2e` contra RabbitMQ Docker local e três processos
Python reais, em um vhost exclusivo. O teste não usa mocks de broker nem os dados
de contas da sessão manual. Veja `resultado-testes.json` para data e casos.

| Arquivo | Conteúdo |
|---|---|
| `transferencia-assincrona.png` | Saídas reais: débito, envio, crédito e confirmação |
| `resiliencia-fila.png` | Fila com destino desligado e falha de conta ausente após reinício |
| `linha-do-tempo-causal.png` | Saída real do script em experimento sem reinícios |
| `funcionalidade-adicional.png` | Interface real com crédito confirmado |
| `frontend-resumo.png` | Resumo e saldo real consultado |
| `frontend-mobile.png` | Histórico em 360 px |
| `frontend-pendente.png` | Pedido aceito enquanto o destino está offline |
| `frontend-falha.png` | Resultado de crédito não aplicado |

As três primeiras imagens são relatórios visuais gerados com os logs/saídas
capturados e `Get-Date -Format o` executado no PowerShell. São distintos de
screenshots de terminal nativo. Não foram usados protótipos como evidência.

## Capturar terminais nativos para a entrega

1. `docker compose up -d --wait`; instalar dependências conforme o README raiz.
2. Abrir três terminais e executar `scripts/iniciar-agencia.ps1 -Agencia 0/1/2`.
   O script imprime `Get-Date` no início.
3. Pelo frontend, criar 300 na Agência 0 e 301 na Agência 1. Transferir e capturar
   os logs das duas agências e a confirmação na interface.
4. Antes de misturar reinícios, executar `uv run python mesclar_logs.py` em um
   quarto terminal, com `Get-Date`; capturar o par de criações concorrentes.
5. Criar 304 na Agência 1; encerrar somente esse processo. Publicar para 304
   pela Agência 0. Capturar a interface pendente e RabbitMQ Manager com fila pronta.
6. Reiniciar Agência 1 sem recriar 304; capturar o log de conta não encontrada
   e o status de falha na interface. O débito permanece aplicado.

Não incluir credenciais de CloudAMQP ou tokens JWT nos prints. Separar logs por
`PASTA_DADOS` ao repetir o experimento causal; o script não compara sessões após
reinício como se fossem uma execução contínua. Os prints da sprint1 foram preservados.
