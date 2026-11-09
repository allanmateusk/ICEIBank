import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:iceibank_mobile/api.dart';
import 'package:iceibank_mobile/main.dart';
import 'package:iceibank_mobile/storage.dart';

class MemoryStorage extends Storage {
  final rows = <Map<String, Object?>>[{
    'ordem': 1, 'conta': 300, 'estado': 'PENDENTE',
    'dados': jsonEncode({'operacaoId': 'uuid-fixo', 'contaId': 300,
      'tipo': 'DEPOSITO', 'valor': 10, 'vetorBase': [1, 0, 0],
      'sessaoServidor': 'sessao-original'}),
  }];
  String? perfilConcluido;
  @override
  Future<List<Map<String, Object?>>> pendentes(String usuario, {int? conta}) async =>
      rows.where((r) => conta == null || r['conta'] == conta).map((r) => Map<String, Object?>.from(r)).toList();
  @override
  Future<void> falha(int ordem, String estado, String erro) async {
    rows.first['estado'] = estado;
  }
  @override
  Future<void> concluir(String usuario, Map<String, Object?> item, Map<String, dynamic> conta,
      {Map<String, dynamic>? transferencia}) async {
    perfilConcluido = usuario;
    rows.clear();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('dev.fluttercommunity.plus/connectivity_status'), (_) async => null);
  });

  testWidgets('resposta de sessão encerrada não sobrescreve a nova sessão', (tester) async {
    final store = MemoryStorage();
    final response = Completer<http.Response>();
    await tester.pumpWidget(MaterialApp(home: Banking(storage: store)));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.api = Api('original', client: MockClient((_) => response.future));
    state.account.text = '300';
    final Future<void> envio = state.sincronizar();
    await tester.pump();
    await state.sair();
    // Mesmo perfil e conta, mas uma sessão nova: comparar apenas o nome não basta.
    state.usuario = 'allan';
    state.api = Api('original');
    state.conta = <String, dynamic>{'id': 300, 'saldo': 999};
    state.status = 'Nova sessão';
    response.complete(http.Response('{"conta":{"id":300,"saldo":110}}', 200));
    await tester.pump();
    await envio;
    expect(store.perfilConcluido, 'original|allan');
    expect(state.conta['saldo'], 999);
    expect(state.status, 'Nova sessão');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('resposta perdida mantém UUID e impede dupla projeção do saldo', (tester) async {
    final store = MemoryStorage();
    final pedidos = <String>[];
    final estadosNoEnvio = <Object?>[];
    var perderResposta = true;
    await tester.pumpWidget(MaterialApp(home: Banking(storage: store)));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.usuario = 'allan';
    state.account.text = '300';
    state.api = Api('original', client: MockClient((request) async {
      pedidos.add(request.body);
      estadosNoEnvio.add(store.rows.first['estado']);
      if (perderResposta) throw TimeoutException('Resposta perdida após aplicar depósito');
      return http.Response('{"conta":{"id":300,"saldo":110}}', 200);
    }));
    // Antes de enviar, a UI pode projetar a operação exclusivamente local.
    expect(projetarSaldo({'id': 300, 'saldo': 100}, store.rows), 110);
    final Future<void> envio = state.sincronizar();
    await tester.pump();
    await envio;
    expect(store.rows.first['estado'], 'INCERTA');
    // Uma consulta posterior já inclui o depósito aplicado pelo servidor.
    state.conta = <String, dynamic>{'id': 300, 'saldo': 110};
    expect(state.saldoEstimado, isNull);
    perderResposta = false;
    final Future<void> retry = state.sincronizar();
    await tester.pump();
    await retry;
    expect(pedidos, hasLength(2));
    expect(estadosNoEnvio, ['INCERTA', 'INCERTA']);
    expect(pedidos[1], pedidos[0]);
    expect(state.saldoEstimado, 110);
    await tester.pumpWidget(const SizedBox());
  });
}
