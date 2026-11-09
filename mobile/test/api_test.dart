import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:iceibank_mobile/api.dart';

void main() {
  test('envia autenticação e conteúdo para a agência correta', () async {
    final api = Api('10.0.2.2', client: MockClient((request) async {
      expect(request.url.toString(), 'http://10.0.2.2:4001/sincronizacao');
      expect(request.method, 'POST');
      expect(request.headers['authorization'], 'Bearer token');
      expect(jsonDecode(request.body), {'tipo': 'DEPOSITO'});
      return http.Response('{"status":"SINCRONIZADA"}', 200);
    }))..token = 'token';

    expect(await api.request(1, '/sincronizacao', body: {'tipo': 'DEPOSITO'}),
        {'status': 'SINCRONIZADA'});
  });

  test('preserva detalhes do conflito para exibição', () async {
    final api = Api('localhost', client: MockClient((_) async => http.Response(
        '{"detail":{"codigo":"VERSAO_CONFLITANTE"}}', 409)));

    await expectLater(
      api.request(0, '/sincronizacao', body: {'tipo': 'SAQUE'}),
      throwsA(isA<ApiError>()
          .having((e) => e.status, 'status', 409)
          .having((e) => (e.data as Map)['detail']['codigo'], 'codigo',
              'VERSAO_CONFLITANTE')),
    );
  });
}
