import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:iceibank_mobile/api.dart';
import 'package:iceibank_mobile/main.dart';
import 'package:iceibank_mobile/storage.dart';

class Store extends Storage {
  @override
  Future<List<Map<String, Object?>>> pendentes(String usuario, {int? conta}) async => [];
  @override
  Future<List<Map<String, Object?>>> transferencias(String usuario) async => [];
}
class SeguroLento extends FlutterSecureStorage {
  final dados = <String, String>{};
  final iniciou = Completer<void>();
  final liberar = Completer<void>();
  @override
  Future<String?> read({required String key, IOSOptions? iOptions, AndroidOptions? aOptions,
      LinuxOptions? lOptions, WebOptions? webOptions, MacOsOptions? mOptions, WindowsOptions? wOptions}) async => dados[key];
  @override
  Future<void> write({required String key, required String? value, IOSOptions? iOptions, AndroidOptions? aOptions,
      LinuxOptions? lOptions, WebOptions? webOptions, MacOsOptions? mOptions, WindowsOptions? wOptions}) async {
    if (!iniciou.isCompleted) { iniciou.complete(); await liberar.future; }
    if (value != null) dados[key] = value;
  }
  @override
  Future<void> deleteAll({IOSOptions? iOptions, AndroidOptions? aOptions, LinuxOptions? lOptions,
      WebOptions? webOptions, MacOsOptions? mOptions, WindowsOptions? wOptions}) async { dados.clear(); }
}
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('login atrasado não troca token da sessão atual', (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/connectivity_status'), (_) async => null);
    final primeiro = Completer<http.Response>();
    final segundo = Completer<http.Response>();
    final cliente = MockClient((req) async {
      if (req.url.path == '/auth/login') {
        final usuario = (jsonDecode(req.body) as Map)['usuario'];
        return usuario == 'primeiro' ? primeiro.future : segundo.future;
      }
      return http.Response('{"liderId":2}', 200);
    });
    await tester.pumpWidget(MaterialApp(home: Banking(storage: Store(), consultarConectividade: () async => [ConnectivityResult.none], criarApi: (host) => Api(host, client: cliente))));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.host.text = 'servidor-antigo'; state.user.text = 'primeiro'; state.password.text = 'senha-1';
    final Future<void> tentativa1 = state.login();
    await tester.pump();
    state.host.text = 'servidor-novo'; state.user.text = 'segundo'; state.password.text = 'senha-2';
    final Future<void> tentativa2 = state.login();
    await tester.pump();
    segundo.complete(http.Response('{"access_token":"token-segundo"}', 200));
    for (var i = 0; i < 20; i++) { await tester.pump(); }
    await tentativa2;
    primeiro.complete(http.Response('{"access_token":"token-primeiro"}', 200));
    for (var i = 0; i < 20; i++) { await tester.pump(); }
    await tentativa1;
    expect(state.usuario, 'segundo');
    expect(state.api.token, 'token-segundo');
    expect(state.api.host, 'servidor-novo');
    expect(await const FlutterSecureStorage().read(key: 'usuario'), 'segundo');
    expect(await const FlutterSecureStorage().read(key: 'host'), 'servidor-novo');
    expect(await const FlutterSecureStorage().read(key: 'jwt'), 'token-segundo');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('resposta de login anterior ao logout não restaura sessão', (tester) async {
    FlutterSecureStorage.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/connectivity_status'), (_) async => null);
    final resposta = Completer<http.Response>();
    final cliente = MockClient((req) => resposta.future);
    await tester.pumpWidget(MaterialApp(home: Banking(storage: Store(),
        consultarConectividade: () async => [ConnectivityResult.none],
        criarApi: (host) => Api(host, client: cliente))));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.user.text = 'primeiro'; state.password.text = 'senha-1';
    final Future<void> tentativa = state.login();
    await tester.pump();
    final Future<void> logout = state.sair();
    for (var i = 0; i < 10; i++) { await tester.pump(); }
    await logout;
    resposta.complete(http.Response('{"access_token":"token-antigo"}', 200));
    for (var i = 0; i < 10; i++) { await tester.pump(); }
    await tentativa;
    expect(state.usuario, isNull);
    expect(state.api.token, isNull);
    expect(await const FlutterSecureStorage().read(key: 'jwt'), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('logout durante gravação não deixa credenciais antigas', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/connectivity_status'), (_) async => null);
    final seguro = SeguroLento();
    final cliente = MockClient((req) async => http.Response('{"access_token":"token-antigo"}', 200));
    await tester.pumpWidget(MaterialApp(home: Banking(storage: Store(), armazenamentoSeguro: seguro,
        consultarConectividade: () async => [ConnectivityResult.none], criarApi: (host) => Api(host, client: cliente))));
    await tester.pump();
    final dynamic state = tester.state(find.byType(Banking));
    state.user.text = 'primeiro'; state.password.text = 'senha-1';
    final Future<void> tentativa = state.login();
    for (var i = 0; i < 10; i++) { await tester.pump(); }
    expect(seguro.iniciou.isCompleted, isTrue);
    final Future<void> logout = state.sair();
    await tester.pump();
    seguro.liberar.complete();
    for (var i = 0; i < 30; i++) { await tester.pump(); }
    await tentativa;
    await logout;
    expect(seguro.dados, isEmpty);
    expect(state.usuario, isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
