import 'dart:convert';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:iceibank_mobile/api.dart';
import 'package:iceibank_mobile/main.dart';
import 'package:iceibank_mobile/storage.dart';

class FilaEmMemoria extends Storage {
  final rows = <Map<String, Object?>>[];
  Map<String, dynamic>? contaSalva;
  @override
  Future<void> salvarConta(String usuario, Map<String, dynamic> conta) async { contaSalva = conta; }
  @override
  Future<List<Map<String, Object?>>> pendentes(String usuario, {int? conta}) async => rows
      .where((r) => conta == null || r['conta'] == conta)
      .map((r) => Map<String, Object?>.from(r)).toList();
  @override
  Future<void> enfileirar(String usuario, Map<String, dynamic> op) async {
    rows.add({'ordem': rows.length + 1, 'conta': op['contaId'], 'estado': 'PENDENTE', 'dados': jsonEncode(op)});
  }
  @override
  Future<void> falha(int ordem, String estado, String erro) async {
    rows.firstWhere((r) => r['ordem'] == ordem).addAll({'estado': estado, 'erro': erro});
  }
  @override
  Future<void> concluir(String usuario, Map<String, Object?> item, Map<String, dynamic> conta,
      {Map<String, dynamic>? transferencia}) async {
    rows.removeWhere((r) => r['ordem'] == item['ordem']);
    if (rows.isNotEmpty) {
      final op = Map<String, dynamic>.from(jsonDecode(rows.first['dados'] as String));
      op['vetorBase'] = conta['vetorVersao'];
      op['sessaoServidor'] = conta['sessaoServidor'];
      rows.first['dados'] = jsonEncode(op);
    }
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/connectivity_status'), (_) async => null);
  });

  testWidgets('layout compacto mantém avisos acessíveis com teclado aberto', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 640));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(viewInsets: const EdgeInsets.only(bottom: 250)),
        child: child!),
      home: Banking(storage: FilaEmMemoria())));
    await tester.pump();
    await tester.ensureVisible(find.text('Criar usuário'));
    await tester.pump();
    await tester.tap(find.text('Criar usuário'));
    await tester.pump();
    await tester.ensureVisible(find.text('Cadastrar'));
    await tester.pump();
    await tester.tap(find.text('Cadastrar'));
    await tester.pump();
    expect(find.text('Usuário deve ter de 3 a 40 letras, números ou . _ -'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('permite cadastrar usuário novo sem credenciais padrão', (tester) async {
    final pedidos = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: Banking(storage: FilaEmMemoria(),
      criarApi: (host) => Api(host, client: MockClient((req) async {
        if (req.method == 'GET') return http.Response('{}', 200);
        pedidos.add(Map<String, dynamic>.from(jsonDecode(req.body)));
        return http.Response('{"usuario":"pessoa_nova"}', 201);
      })))));
    await tester.pump();
    await tester.ensureVisible(find.text('Criar usuário'));
    await tester.pump();
    await tester.tap(find.text('Criar usuário'));
    await tester.pump();
    await tester.enterText(find.widgetWithText(TextField, 'Usuário'), 'pessoa_nova');
    await tester.enterText(find.widgetWithText(TextField, 'Senha'), 'senha-segura');
    await tester.enterText(find.widgetWithText(TextField, 'Confirmar senha'), 'senha-diferente');
    await tester.ensureVisible(find.text('Cadastrar'));
    await tester.pump();
    await tester.tap(find.text('Cadastrar'));
    await tester.pump();
    expect(pedidos, isEmpty);
    expect(find.text('As senhas não conferem.'), findsOneWidget);
    await tester.ensureVisible(find.widgetWithText(TextField, 'Confirmar senha'));
    await tester.pump();
    await tester.enterText(find.widgetWithText(TextField, 'Confirmar senha'), 'senha-segura');
    await tester.ensureVisible(find.text('Cadastrar'));
    await tester.pump();
    await tester.tap(find.text('Cadastrar'));
    await tester.pump();
    await tester.pump();
    expect(pedidos, [{'usuario': 'pessoa_nova', 'senha': 'senha-segura'}]);
    expect(find.text('Usuário criado. Entre com suas credenciais.'), findsOneWidget);
    expect(find.text('Entrar'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('operações offline mantêm saldo otimista e sincronizam em ordem', (tester) async {
    final store = FilaEmMemoria();
    var online = false;
    var saldo = 100.0;
    final enviados = <Map<String, dynamic>>[];
    await tester.pumpWidget(MaterialApp(home: Banking(storage: store,
        consultarConectividade: () async => [online ? ConnectivityResult.wifi : ConnectivityResult.none])));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.account.text = '300';
    state.conta = <String, dynamic>{'id': 300, 'saldo': 100.0, 'vetorVersao': [1, 0, 0], 'sessaoServidor': 's'};
    state.api = Api('servidor', client: MockClient((req) async {
      if (req.method == 'GET') return http.Response('{}', 200);
      final op = Map<String, dynamic>.from(jsonDecode(req.body));
      enviados.add(op);
      saldo += (op['tipo'] == 'DEPOSITO' ? 1 : -1) * (op['valor'] as num);
      return http.Response(jsonEncode({'conta': {'id': 300, 'saldo': saldo,
        'vetorVersao': [enviados.length + 1, 0, 0], 'sessaoServidor': 's'}}), 200);
    }));
    for (final valor in ['10', '5']) {
      state.amount.text = valor;
      final Future<void> acao = state.movimentar('DEPOSITO');
      await tester.pump();
      await acao;
    }
    expect(store.rows.length, 2);
    expect(store.rows.map((r) => r['estado']), ['PENDENTE', 'PENDENTE']);
    expect(state.saldoEstimado, 115);
    expect(enviados, isEmpty);
    final ids = store.rows.map((r) => jsonDecode(r['dados'] as String)['operacaoId']).toList();
    online = true;
    final Future<void> envio = state.sincronizar();
    await tester.pump();
    await envio;
    expect(enviados.map((op) => op['operacaoId']), ids);
    expect(enviados[1]['vetorBase'], [2, 0, 0]);
    expect(store.rows, isEmpty);
    expect(state.saldoEstimado, 115);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Wi-Fi ativo com agência indisponível mantém operações locais', (tester) async {
    final store = FilaEmMemoria();
    var posts = 0;
    await tester.pumpWidget(MaterialApp(home: Banking(storage: store,
        consultarConectividade: () async => [ConnectivityResult.wifi])));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.account.text = '300';
    state.conta = <String, dynamic>{'id': 300, 'saldo': 100.0, 'vetorVersao': [1, 0, 0], 'sessaoServidor': 's'};
    state.api = Api('servidor', client: MockClient((req) async {
      if (req.method == 'POST') posts++;
      throw http.ClientException('agência indisponível');
    }));
    for (final valor in ['10', '5']) {
      state.amount.text = valor;
      final Future<void> acao = state.movimentar('DEPOSITO');
      await tester.pump();
      await acao;
    }
    expect(posts, 0);
    expect(store.rows.map((r) => r['estado']), ['PENDENTE', 'PENDENTE']);
    expect(state.saldoEstimado, 115);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('painel distingue eleição ativa de agência indisponível', (tester) async {
    var eleicao = true;
    await tester.pumpWidget(MaterialApp(home: Banking(storage: FilaEmMemoria())));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.api = Api('servidor', client: MockClient((req) async {
      if (req.url.port == 4002 && !eleicao) throw http.ClientException('indisponível');
      return http.Response(jsonEncode({'liderId': req.url.port == 4000 ? 1 : eleicao ? null : 1,
        'emEleicao': eleicao && req.url.port != 4000}), 200);
    }));
    var consulta = state.verificarLider() as Future<void>;
    await tester.pump();
    await consulta;
    expect(state.lider, 'eleição em andamento');
    eleicao = false;
    consulta = state.verificarLider() as Future<void>;
    await tester.pump();
    await consulta;
    expect(state.lider, '1');
    expect(state.diagnostico[2], 'Indisponível');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('conflito 409 é exibido e bloqueia a próxima operação da conta', (tester) async {
    tester.view.physicalSize = const Size(1000, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = FilaEmMemoria();
    for (var i = 0; i < 2; i++) {
      await store.enfileirar('servidor|allan', {'operacaoId': 'op-$i', 'contaId': 300, 'tipo': 'DEPOSITO', 'valor': 10});
    }
    await tester.pumpWidget(MaterialApp(home: Banking(storage: store,
        consultarConectividade: () async => [ConnectivityResult.wifi])));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.account.text = '300';
    state.conta = <String, dynamic>{'id': 300, 'saldo': 100};
    var envios = 0;
    state.api = Api('servidor', client: MockClient((req) async {
      if (req.method == 'GET') return http.Response('{}', 200);
      envios++;
      return http.Response('{"detail":{"codigo":"VERSAO_CONFLITANTE","conta":{"id":300,"saldo":75}}}', 409);
    }));
    final Future<void> envio = state.sincronizar();
    await tester.pump();
    await envio;
    await tester.pump();
    expect(envios, 1);
    expect(store.rows.map((r) => r['estado']), ['CONFLITO', 'PENDENTE']);
    expect(find.textContaining('Conflito na conta 300'), findsOneWidget);
    expect(find.textContaining('saldo atual no servidor: R\$ 75.00'), findsOneWidget);
    expect(store.contaSalva?['saldo'], 75);
    expect(state.conta['saldo'], 75);
    expect(state.saldoEstimado, isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
