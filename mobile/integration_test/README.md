# Ensaio de integração Android

`fluxo_real_test.dart` usa a interface Flutter, o SQLite e o armazenamento
seguro do Android com as três agências, Postgres e RabbitMQ do ambiente de
teste. O ensaio cadastra usuário e contas exclusivos nesse ambiente.

A indisponibilidade de rede é simulada no cliente HTTP e na consulta de
conectividade; o Wi-Fi do aparelho não é alterado. A persistência é conferida
após desmontar e remontar a interface e reabrir o SQLite, no mesmo processo.
Esses passos não substituem um teste de desligar o Wi-Fi nem de encerrar o
processo Android.

O script cria uma cópia temporária do projeto com `applicationId`, namespace
e pacote Kotlin distintos e desativa o uninstall automático. Após esses ajustes,
ele ainda precisa ser validado em dispositivo separado: não execute no aparelho
principal até concluir essa validação. Com o telefone de teste conectado via USB,
backend isolado ativo nas portas 4200–4202 e Flutter/SDK preparados:

```powershell
./mobile/integration_test/executar-isolado.ps1 -DeviceId 'ID_DO_DISPOSITIVO'
```

`adb devices` lista o identificador a usar no lugar de `ID_DO_DISPOSITIVO`.
As credenciais do teste ficam em um namespace separado no pacote de teste.
Os dados de teste permanecem no ambiente isolado até sua limpeza explícita.
O script cria os encaminhamentos ADB necessários e se recusa a sobrescrever
um encaminhamento existente para outro destino. A cópia fica em `.tools/` e
não é removida automaticamente.
