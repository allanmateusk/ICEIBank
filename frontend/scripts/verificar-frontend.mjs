// Teste E2E real. Requer compose ativo, Python da agência instalado e Edge no Windows.
import { chromium } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
const frontend = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const repo = path.resolve(frontend, ".."),
  agenciaDir = path.join(repo, "agencia");
const vhost = `browser-${randomUUID()}`;
const portaBase = 14600;
const pasta = path.join(agenciaDir, "data", vhost);
const evidencia = process.env.EVIDENCIAS_DIR || path.join(repo, "evidencias", "sprint2");
fs.mkdirSync(pasta, { recursive: true });
fs.mkdirSync(evidencia, { recursive: true });
const processos = new Map(),
  saidas = {};
const gestor = "http://127.0.0.1:15678/api";
const auth = "Basic " + Buffer.from("iceibank:iceibank-dev").toString("base64");
const python = path.join(
  agenciaDir,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let browser, token;
async function management(metodo, rota, corpo) {
  const r = await fetch(gestor + rota, {
    method: metodo,
    headers: { Authorization: auth, "Content-Type": "application/json" },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  if (!r.ok) throw new Error(`RabbitMQ Manager ${r.status}: ${rota}`);
  return r.status === 204 || r.status === 201 ? null : r.json();
}
async function api(id, metodo, rota, dados) {
  const r = await fetch(`http://127.0.0.1:${portaBase + id}${rota}`, {
    method: metodo,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: dados ? JSON.stringify(dados) : undefined,
  });
  const corpo = await r.json();
  if (!r.ok) throw new Error(`API ${r.status}: ${JSON.stringify(corpo)}`);
  return corpo;
}
async function ready(url, p) {
  for (let i = 0; i < 100; i++) {
    if (p.exitCode !== null) throw new Error(`Processo encerrado: ${url}`);
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await sleep(150);
  }
  throw new Error(`Servidor não iniciou: ${url}`);
}
async function iniciar(id) {
  saidas[id] ||= "";
  const p = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "src.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(portaBase + id),
    ],
    {
      cwd: agenciaDir,
      windowsHide: true,
      env: Object.fromEntries(
        Object.entries({
          ...process.env,
          AGENCIA_ID: String(id),
          OFFSET: String(portaBase - 4000),
          PASTA_DADOS: pasta,
          PYTHONUNBUFFERED: "1",
          RABBITMQ_URL: `amqp://iceibank:iceibank-dev@127.0.0.1:5678/${vhost}`,
        }).filter(([chave]) => chave !== "DATABASE_URL"),
      ),
    },
  );
  processos.set(id, p);
  p.stdout.on("data", (b) => {
    saidas[id] += b.toString();
  });
  p.stderr.on("data", (b) => {
    saidas[id] += b.toString();
  });
  await ready(`http://127.0.0.1:${portaBase + id}/`, p);
}
async function parar(id) {
  const p = processos.get(id);
  if (p && p.exitCode === null) {
    const done = new Promise((r) => p.once("exit", r));
    p.kill();
    await done;
  }
}
const escape = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function capturarRelatorio(nome, titulo, texto) {
  const data =
    process.platform === "win32"
      ? execFileSync(
          "powershell.exe",
          ["-NoProfile", "-Command", "Get-Date -Format o"],
          { windowsHide: true },
        )
          .toString()
          .trim()
      : new Date().toISOString();
  const p = await browser.newPage({ viewport: { width: 1300, height: 900 } });
  await p.setContent(
    `<html lang="pt-BR"><meta charset="utf-8"><style>body{background:#101712;color:#eaf3ec;font:15px/1.55 Consolas,monospace;padding:32px}h1{font:26px system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}.data{color:#a4f077}</style><h1>${escape(titulo)}</h1><p class="data">PowerShell &gt; Get-Date -Format o<br>${escape(data)}</p><p>Saída capturada da execução real · RabbitMQ e três processos FastAPI</p><pre>${escape(texto)}</pre></html>`,
  );
  await p.screenshot({ path: path.join(evidencia, nome), fullPage: true });
  await p.close();
}
try {
  await management("PUT", `/vhosts/${vhost}`, {});
  await management("PUT", `/permissions/${vhost}/iceibank`, {
    configure: ".*",
    write: ".*",
    read: ".*",
  });
  for (let id = 0; id < 3; id++) await iniciar(id);
  token = (
    await api(0, "POST", "/auth/login", { usuario: "allan", senha: "iceibank" })
  ).access_token;
  await Promise.all(
    [300, 301, 302].map((id) =>
      api(id % 3, "POST", "/contas", {
        id,
        nomeAluno: "Allan",
        saldoInicial: id === 300 ? 2450.75 : 10,
      }),
    ),
  );
  const vite = spawn(
    process.execPath,
    [
      path.join(frontend, "node_modules/vite/bin/vite.js"),
      "--host",
      "127.0.0.1",
      "--port",
      "15173",
      "--strictPort",
    ],
    {
      cwd: frontend,
      windowsHide: true,
      env: { ...process.env, VITE_OFFSET: String(portaBase - 4000) },
    },
  );
  processos.set("vite", vite);
  vite.stdout.on("data", () => {});
  vite.stderr.on("data", () => {});
  await ready("http://127.0.0.1:15173", vite);
  browser = await chromium.launch({
    headless: true,
    ...(process.platform === "win32"
      ? { channel: process.env.BROWSER_CHANNEL || "msedge" }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1360, height: 1000 },
  });
  const erros = [];
  page.on("pageerror", (e) => erros.push(e.message));
  await page.goto("http://127.0.0.1:15173", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Usuário", { exact: true }).fill("allan");
  await page.getByLabel("Senha", { exact: true }).fill("iceibank");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("heading", { name: "Meu dinheiro" }).waitFor();
  await page
    .getByRole("button", { name: "Consultar conta", exact: true })
    .click();
  await page.getByLabel("Número da conta", { exact: true }).fill("300");
  await page.getByRole("button", { name: "Consultar", exact: true }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Resumo", exact: true })
    .click();
  await page.locator(".saldo-valor").filter({ hasText: "2.450,75" }).waitFor();
  await page.screenshot({
    path: path.join(evidencia, "frontend-resumo.png"),
    fullPage: true,
  });
  await page
    .locator(".saldo-card")
    .getByRole("button", { name: "Depositar", exact: true })
    .click();
  await page.getByLabel("Valor (R$)", { exact: true }).fill("10,00");
  await page.getByRole("button", { name: "Depositar", exact: true }).click();
  await page.locator(".saldo-valor").filter({ hasText: "2.460,75" }).waitFor();
  await page
    .locator(".saldo-card")
    .getByRole("button", { name: "Sacar", exact: true })
    .click();
  await page.getByLabel("Valor (R$)", { exact: true }).fill("10,00");
  await page.getByRole("button", { name: "Sacar", exact: true }).click();
  await page.locator(".saldo-valor").filter({ hasText: "2.450,75" }).waitFor();
  await page
    .locator("nav")
    .getByRole("button", { name: "Criar conta", exact: true })
    .click();
  await page.getByLabel("Número da conta", { exact: true }).fill("303");
  await page.getByLabel("Nome do aluno", { exact: true }).fill("Allan");
  await page.getByLabel("Saldo inicial (R$)", { exact: true }).fill("25,00");
  await page.getByRole("button", { name: "Criar", exact: true }).click();
  await page.locator(".saldo-valor").filter({ hasText: "25,00" }).waitFor();
  await page
    .getByRole("button", { name: "Consultar outra conta", exact: true })
    .click();
  await page.getByLabel("Número da conta", { exact: true }).fill("300");
  await page.getByRole("button", { name: "Consultar", exact: true }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Resumo", exact: true })
    .click();
  await page.locator(".saldo-valor").filter({ hasText: "2.450,75" }).waitFor();
  await page
    .locator("nav")
    .getByRole("button", { name: "Transferir", exact: true })
    .click();
  await page.getByLabel("Conta de destino", { exact: true }).fill("301");
  await page.getByLabel("Valor (R$)", { exact: true }).fill("150,00");
  await page.getByRole("button", { name: "Revisar transferência" }).click();
  await page.getByRole("button", { name: "Confirmar envio" }).click();
  await page
    .locator(".acompanhamento .badge")
    .filter({ hasText: "Crédito confirmado" })
    .waitFor();
  assert.equal(
    await page
      .getByText("Mensagem publicada. Aguardando confirmação do crédito.", {
        exact: true,
      })
      .count(),
    0,
  );
  await page.screenshot({
    path: path.join(evidencia, "funcionalidade-adicional.png"),
    fullPage: true,
  });
  assert.equal((await api(1, "GET", "/contas/301")).saldo, 160);
  await page
    .locator("nav")
    .getByRole("button", { name: "Histórico", exact: true })
    .click();
  await page
    .locator(".historico .badge")
    .filter({ hasText: "Crédito confirmado" })
    .waitFor();
  await page.setViewportSize({ width: 360, height: 900 });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  );
  await page.screenshot({
    path: path.join(evidencia, "frontend-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1360, height: 1000 });
  const timeline = execFileSync(
    python,
    ["mesclar_logs.py", "--pasta", pasta, "--limite-pares", "50"],
    { cwd: agenciaDir, encoding: "utf8", windowsHide: true },
  );
  assert(
    timeline
      .split("\n")
      .some(
        (l) =>
          l.includes("agencia-0 CRIAR_CONTA [1, 0, 0]") &&
          l.includes("agencia-1 CRIAR_CONTA [0, 1, 0]"),
      ),
  );
  await capturarRelatorio(
    "linha-do-tempo-causal.png",
    "Linha do tempo causal — experimento sem reinício",
    timeline,
  );
  const logEventos = Object.values(saidas)
    .join("\n")
    .split("\n")
    .filter((l) => l.includes("[Vetor"))
    .join("\n");
  await capturarRelatorio(
    "transferencia-assincrona.png",
    "Transferência assíncrona — publicação, crédito e confirmação",
    logEventos,
  );
  await api(1, "POST", "/contas", {
    id: 304,
    nomeAluno: "Allan",
    saldoInicial: 20,
  });
  await parar(1);
  await page
    .locator("nav")
    .getByRole("button", { name: "Transferir", exact: true })
    .click();
  await page.getByLabel("Conta de destino", { exact: true }).fill("304");
  await page.getByLabel("Valor (R$)", { exact: true }).fill("10,00");
  await page.getByRole("button", { name: "Revisar transferência" }).click();
  await page.getByRole("button", { name: "Confirmar envio" }).click();
  await page
    .locator(".acompanhamento .badge")
    .filter({ hasText: "Aguardando crédito" })
    .waitFor();
  await page.screenshot({
    path: path.join(evidencia, "frontend-pendente.png"),
    fullPage: true,
  });
  let fila;
  for (let i = 0; i < 80; i++) {
    fila = await management("GET", `/queues/${vhost}/fila-agencia-1`);
    if (fila.consumers === 0 && fila.messages_ready >= 1) break;
    await sleep(200);
  }
  assert.equal(fila.consumers, 0);
  assert(fila.messages_ready >= 1);
  await iniciar(1);
  await page
    .locator(".acompanhamento .badge")
    .filter({ hasText: "Crédito não aplicado" })
    .waitFor();
  await page.screenshot({
    path: path.join(evidencia, "frontend-falha.png"),
    fullPage: true,
  });
  await capturarRelatorio(
    "resiliencia-fila.png",
    "Resiliência — mensagem preservada, conta perdida no reinício",
    `Agência 1 desligada: consumidores=${fila.consumers}, mensagens prontas=${fila.messages_ready}, fila durável=${fila.durable}\n${Object.values(
      saidas,
    )
      .join("\n")
      .split("\n")
      .filter((l) =>
        /CREDITO_REMOTO_FALHOU|CONFIRMACAO_RECEBIDA|TRANSFERENCIA_DEBITO/.test(
          l,
        ),
      )
      .join("\n")}`,
  );
  // Regressões: histórico local e recuperação de resposta perdida sem novo débito.
  await api(0, "POST", "/transferencias", {
    idOrigem: 300,
    idDestino: 303,
    valor: 5,
  });
  const hOrigem = await api(0, "GET", "/contas/300/historico");
  const hDestino = await api(0, "GET", "/contas/303/historico");
  const tiposLocais = (h) =>
    h.eventos
      .filter(
        (e) => e.detalhes.idOrigem === 300 && e.detalhes.idDestino === 303,
      )
      .map((e) => e.tipo);
  assert.deepEqual(tiposLocais(hOrigem), ["TRANSFERENCIA_DEBITO"]);
  assert.deepEqual(tiposLocais(hDestino), ["TRANSFERENCIA_CREDITO"]);
  await page
    .locator("nav")
    .getByRole("button", { name: "Histórico", exact: true })
    .click();
  await page.locator(".movimentacao").first().waitFor();
  assert.equal(
    await page.getByText("Transferência recebida", { exact: true }).count(),
    0,
  );
  await page.screenshot({
    path: path.join(evidencia, "regressao-historico-local.png"),
    fullPage: true,
  });
  await page
    .locator("nav")
    .getByRole("button", { name: "Transferir", exact: true })
    .click();
  await page.getByLabel("Conta de destino", { exact: true }).fill("303");
  await page.getByLabel("Valor (R$)", { exact: true }).fill("7,00");
  await page.getByRole("button", { name: "Revisar transferência" }).click();
  const saldoAntes = (await api(0, "GET", "/contas/300")).saldo;
  const chaves = [];
  const perderResposta = async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    chaves.push(route.request().headers()["idempotency-key"]);
    await route.fetch();
    await route.abort("connectionreset");
  };
  await page.route("**/transferencias", perderResposta);
  await page
    .getByRole("button", { name: "Confirmar envio", exact: true })
    .click();
  await page
    .getByText("Não foi possível falar com a agência. Ela está no ar?", {
      exact: true,
    })
    .waitFor();
  await page.unroute("**/transferencias", perderResposta);
  assert.equal(
    (await api(0, "GET", "/contas/300")).saldo,
    +(saldoAntes - 7).toFixed(2),
  );
  assert(
    await page
      .getByRole("button", { name: "Editar", exact: true })
      .isDisabled(),
  );
  assert(await page.getByLabel("Valor (R$)", { exact: true }).isDisabled());
  await page
    .locator("nav")
    .getByRole("button", { name: "Resumo", exact: true })
    .click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Transferir", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Recuperar resultado", exact: true })
    .waitFor();
  await page.reload();
  await page
    .getByRole("button", { name: "Consultar conta", exact: true })
    .click();
  await page.getByLabel("Número da conta", { exact: true }).fill("300");
  await page.getByRole("button", { name: "Consultar", exact: true }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Transferir", exact: true })
    .click();
  await api(0, "POST", "/contas/300/depositar", { valor: 100 });
  const saldoAtual = (await api(0, "GET", "/contas/300")).saldo;
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().endsWith("/transferencias"))
      chaves.push(req.headers()["idempotency-key"]);
  });
  await page
    .getByRole("button", { name: "Recuperar resultado", exact: true })
    .click();
  await page.getByRole("button", { name: "Revisar transferência" }).waitFor();
  assert.deepEqual(chaves, [chaves[0], chaves[0]]);
  assert.equal((await api(0, "GET", "/contas/300")).saldo, saldoAtual);
  await page
    .locator("nav")
    .getByRole("button", { name: "Resumo", exact: true })
    .click();
  const saldoEsperado = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(saldoAtual);
  assert.equal(await page.locator(".saldo-valor").innerText(), saldoEsperado);
  await page.screenshot({
    path: path.join(evidencia, "regressao-recuperacao-saldo.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await page.getByRole("heading", { name: "Entrar", exact: true }).waitFor();
  assert.deepEqual(erros, []);
  fs.writeFileSync(
    path.join(evidencia, "resultado-testes.json"),
    JSON.stringify(
      {
        data: new Date().toISOString(),
        casos: [
          "login JWT",
          "saldo",
          "criar conta",
          "depósito",
          "saque",
          "transferência com confirmação real",
          "histórico",
          "mobile 360px",
          "concorrência vetorial",
          "destino offline",
          "conta perdida após reinício",
          "logout",
          "histórico local sem crédito na origem",
          "resposta perdida: mesmo UUID após navegação e reload",
          "saldo atual após repetição e depósito concorrente",
        ],
        errosJavaScript: erros,
      },
      null,
      2,
    ),
  );
  console.log(
    "OK: frontend real + 3 agências + RabbitMQ; confirmações, pendência, falha, histórico, mobile e evidências verificadas.",
  );
} finally {
  if (browser) await browser.close();
  for (const id of processos.keys()) await parar(id);
  await management("DELETE", `/vhosts/${vhost}`).catch(() => {});
}
