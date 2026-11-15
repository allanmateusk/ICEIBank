// Teste em Android: backend HTTP e SQLite reais. A perda de conectividade é
// simulada pelo cliente HTTP e pela consulta de conectividade injetados.
// Execute somente contra um ambiente de teste isolado.
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:iceibank_mobile/api.dart';
import 'package:iceibank_mobile/main.dart';
import 'package:iceibank_mobile/storage.dart';
import 'package:integration_test/integration_test.dart';

class RedeControlada extends http.BaseClient {
  RedeControlada(this.disponivel);
  final bool Function() disponivel;
  final _real = http.Client();
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    if (!disponivel()) throw http.ClientException('Rede desligada pelo teste');
    return _real.send(request);
  }
  @override
  void close() => _real.close();
}

Future<void> aguardar(WidgetTester tester, bool Function() pronto,
    {String descricao = 'condição', int segundos = 15}) async {
  for (var i = 0; i < segundos * 5; i++) {
    await tester.pump(const Duration(milliseconds: 200));
    if (pronto()) return;
  }
  final banking = find.byType(Banking);
  if (banking.evaluate().isNotEmpty) {
    final dynamic state = tester.state(banking);
    fail('Tempo esgotado aguardando $descricao; estado=${state.status}; '
        'conta=${state.account.text}; valor=${state.amount.text}; fila=${state.fila}');
  }
  fail('Tempo esgotado aguardando $descricao');
}

Future<void> tocar(WidgetTester tester, Finder alvo) async {
  FocusManager.instance.primaryFocus?.unfocus();
  await tester.pump(const Duration(milliseconds: 500));
  await Scrollable.ensureVisible(tester.element(alvo), alignment: .5);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.tap(alvo);
  await tester.pump();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Android: login, operações, fila SQLite e conflito real', (tester) async {
    const servidor = '127.0.0.1';
    final sufixo = DateTime.now().microsecondsSinceEpoch;
    final usuario = 'teste_${sufixo.toRadixString(36)}';
    final senha = 'teste_${sufixo.toRadixString(36)}';
    final origem = (sufixo % 100000000) * 3;
    final destino = origem + 1;
    final clienteFixture = http.Client();
    Future<Map<String, dynamic>> post(int agencia, String caminho,
        Map<String, dynamic> body, {String? token}) async {
      final r = await clienteFixture.post(Uri.parse('http://$servidor:${4000 + agencia}$caminho'),
          headers: {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'},
          body: jsonEncode(body)).timeout(const Duration(seconds: 10));
      expect(r.statusCode, inInclusiveRange(200, 299), reason: '$caminho: ${r.body}');
      return Map<String, dynamic>.from(jsonDecode(r.body) as Map);
    }
    Future<Map<String, dynamic>> obter(int agencia, int conta, String token) async {
      final r = await clienteFixture.get(Uri.parse('http://$servidor:${4000 + agencia}/contas/$conta'),
          headers: {'Authorization': 'Bearer $token'}).timeout(const Duration(seconds: 10));
      expect(r.statusCode, 200, reason: r.body);
      return Map<String, dynamic>.from(jsonDecode(r.body) as Map);
    }

    await post(0, '/auth/cadastro', {'usuario': usuario, 'senha': senha});
    final token = (await post(0, '/auth/login', {'usuario': usuario, 'senha': senha}))['access_token'] as String;
    await post(0, '/contas', {'id': origem, 'nomeAluno': 'Android teste', 'saldoInicial': 100}, token: token);
    await post(1, '/contas', {'id': destino, 'nomeAluno': 'Android destino', 'saldoInicial': 10}, token: token);

    var rede = true;
    var storage = Storage();
    await storage.init();
    // Isola as credenciais deste teste, sem limpar ou sobrescrever a sessão
    // que já existe no aplicativo (mesmo quando o teste usa outro pacote).
    final seguro = FlutterSecureStorage(aOptions: AndroidOptions(
      sharedPreferencesName: 'iceibank_integration_$sufixo',
      preferencesKeyPrefix: 'teste_$sufixo'));
    final clientes = <RedeControlada>[];
    Widget app() => MaterialApp(home: Banking(storage: storage, armazenamentoSeguro: seguro,
      consultarConectividade: () async => [rede ? ConnectivityResult.wifi : ConnectivityResult.none],
      criarApi: (host) {
        final cliente = RedeControlada(() => rede);
        clientes.add(cliente);
        return Api(host, client: cliente);
      }));
    addTearDown(() async { for (final c in clientes) { c.close(); } clienteFixture.close(); });

    await tester.pumpWidget(app());
    await tester.pump(const Duration(seconds: 1));
    await tester.enterText(find.widgetWithText(TextField, 'Usuário'), usuario);
    await tester.enterText(find.widgetWithText(TextField, 'Senha'), senha);
    await tester.ensureVisible(find.widgetWithText(TextField, 'Host do backend'));
    await tester.enterText(find.widgetWithText(TextField, 'Host do backend'), servidor);
    await tocar(tester, find.text('Entrar'));
    await aguardar(tester, () => find.text('Olá, $usuario').evaluate().isNotEmpty, descricao: 'login');
    await tester.enterText(find.widgetWithText(TextField, 'Número da conta'), '$origem');
    await tocar(tester, find.text('Consultar saldo'));
    await aguardar(tester, () => find.text('R\$ 100.00').evaluate().isNotEmpty, descricao: 'saldo inicial');

    Future<void> movimentar(String tipo, String valor, {int? destinoId}) async {
      final dynamic state = tester.state(find.byType(Banking));
      await aguardar(tester, () => !state.registrandoOperacao,
          descricao: 'fim da operação anterior');
      final campo = find.widgetWithText(TextField, 'Valor');
      await tester.ensureVisible(campo);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(campo);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.enterText(campo, valor);
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.amount.text, valor, reason: 'valor deve estar preenchido antes de tocar $tipo');
      expect(state.account.text, '$origem', reason: 'conta selecionada antes de $tipo');
      if (destinoId != null) {
        await tester.enterText(find.widgetWithText(TextField, 'Conta destino (transferência)'), '$destinoId');
      }
      await tocar(tester, find.text(tipo));
    }

    await movimentar('Depositar', '10');
    await aguardar(tester, () => find.text('R\$ 110.00').evaluate().isNotEmpty, descricao: 'depósito online');
    await movimentar('Sacar', '5');
    await aguardar(tester, () => find.text('R\$ 105.00').evaluate().isNotEmpty, descricao: 'saque online');
    await movimentar('Transferir', '5', destinoId: destino);
    await aguardar(tester, () => find.text('R\$ 100.00').evaluate().isNotEmpty, descricao: 'débito da transferência');
    for (var i = 0; i < 50; i++) {
      if ((await obter(1, destino, token))['saldo'] == 15) break;
      await tester.pump(const Duration(milliseconds: 200));
    }
    expect((await obter(1, destino, token))['saldo'], 15);

    rede = false;
    await movimentar('Depositar', '7');
    final perfil = '$servidor|$usuario';
    await aguardar(tester, () => find.textContaining('Saldo estimado: R\$ 107.00').evaluate().isNotEmpty,
        descricao: 'saldo otimista offline');
    var fila = await storage.pendentes(perfil, conta: origem);
    expect(fila, hasLength(1));
    expect(fila.single['estado'], 'PENDENTE');
    final uuid = (jsonDecode(fila.single['dados'] as String) as Map)['operacaoId'];

    // Desmontar e reabrir o banco real testa persistência no mesmo processo;
    // não equivale a matar o processo Android ou alternar o Wi-Fi do aparelho.
    await tester.pumpWidget(const SizedBox());
    await storage.db.close();
    storage = Storage();
    await storage.init();
    await tester.pumpWidget(app());
    await aguardar(tester, () => find.text('Olá, $usuario').evaluate().isNotEmpty, descricao: 'restauração da sessão');
    fila = await storage.pendentes(perfil, conta: origem);
    expect(fila, hasLength(1));
    expect((jsonDecode(fila.single['dados'] as String) as Map)['operacaoId'], uuid);
    await tester.enterText(find.widgetWithText(TextField, 'Número da conta'), '$origem');
    await tocar(tester, find.text('Consultar saldo'));
    await aguardar(tester, () => find.textContaining('Saldo estimado: R\$ 107.00').evaluate().isNotEmpty,
        descricao: 'saldo armazenado após reconstruir o app');

    rede = true;
    // O timer do próprio aplicativo dispara a sincronização; o teste não chama
    // sincronizar() diretamente.
    for (var i = 0; i < 75; i++) {
      await tester.pump(const Duration(milliseconds: 200));
      if ((await storage.pendentes(perfil, conta: origem)).isEmpty) break;
    }
    expect(await storage.pendentes(perfil, conta: origem), isEmpty);
    expect((await obter(0, origem, token))['saldo'], 107);

    rede = false;
    await movimentar('Depositar', '3');
    await aguardar(tester, () => find.textContaining('Saldo estimado: R\$ 110.00').evaluate().isNotEmpty,
        descricao: 'segunda operação offline');
    await post(0, '/contas/$origem/depositar', {'valor': 2}, token: token);
    rede = true;
    for (var i = 0; i < 75; i++) {
      await tester.pump(const Duration(milliseconds: 200));
      fila = await storage.pendentes(perfil, conta: origem);
      if (fila.isNotEmpty && fila.first['estado'] == 'CONFLITO') break;
    }
    expect(fila.single['estado'], 'CONFLITO');
    expect((await obter(0, origem, token))['saldo'], 109);
    expect(find.textContaining('Conflito na conta'), findsOneWidget);
    await tester.ensureVisible(find.textContaining('CONFLITO'));
    await tester.pump();
    expect(find.textContaining('saldo atual no servidor: R\$ 109.00'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await storage.db.close();
  }, timeout: const Timeout(Duration(minutes: 3)));
}
