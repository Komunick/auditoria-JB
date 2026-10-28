"""Contratos de navegação, consulta e confirmação da Central (Node opcional)."""
from pathlib import Path
import shutil
import subprocess


def main():
    raiz = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        print("PULADO - Central UI: Node não instalado")
        return 0
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const eventos = [], abas = [], etapas = [];
const ctx = {console, URLSearchParams, Abas: {registrar() {}, abrir(nome) {abas.push(nome);}},
  Sessao: {pode: () => true}, CustomEvent: class {constructor(type, v) {this.type=type; this.detail=v.detail;}},
  document: {dispatchEvent(e) {eventos.push(e);}}};
vm.createContext(ctx);
for (const arquivo of ['tarefas.js', 'inicio.js']) vm.runInContext(fs.readFileSync('webui/' + arquivo, 'utf8'), ctx);
const run = codigo => vm.runInContext(codigo, ctx);
assert.strictEqual(run('JSON.stringify(CentralUI.consulta({}))'), '{"visao":"cliente","fila":"pendentes","pagina":1,"limite":10}');
assert.strictEqual(run('JSON.stringify(CentralUI.consulta({visao:"minhas",competencia:"2026-10",texto:"teste"},"atrasadas",2))'), '{"visao":"minhas","competencia":"2026-10","texto":"teste","fila":"atrasadas","pagina":2,"limite":10}');
assert.strictEqual(run('JSON.stringify(TarefasUI.contexto({filtros:{visao:"cliente",cliente_id:7,competencia:"",texto:"teste",autor:9},fila:"conferencia",tarefa_id:11,pode_gerir:true}))'), '{"filtros":{"visao":"cliente","cliente_id":7,"texto":"teste"},"fila":"conferencia","tarefa_id":11}');
assert.throws(() => run('TarefasUI.contexto({fila:"inventada"})'));
run('TarefasUI.abrirContexto({filtros:{competencia:"2026-10",setor_id:2},fila:"sem_vencimento",tarefa_id:3})');
assert.deepStrictEqual(abas, ['tarefas']);
assert.strictEqual(eventos[0].type, 'tarefas:abrir');
assert.strictEqual(JSON.stringify(eventos[0].detail), '{"filtros":{"visao":"cliente","setor_id":2,"competencia":"2026-10"},"fila":"sem_vencimento","tarefa_id":3}');
ctx.Sessao.pode = () => false;
run('TarefasUI.abrirContexto({})');
assert.strictEqual(abas.length, 1);
assert.strictEqual(run('CentralUI.montar({})'), false, 'Sem permissão não monta nem consulta API');
ctx.Sessao.pode = () => true;
const adiar = () => {let resolver, rejeitar; const promise = new Promise((r,j) => {resolver=r; rejeitar=j;}); return {promise,resolver,rejeitar};};
(async () => {
  const s = {}, a = adiar(), b = adiar(); ctx.s=s; ctx.a=a; ctx.b=b;
  const antiga=run('CentralUI.consultar(s, () => a.promise)'), nova=run('CentralUI.consultar(s, () => b.promise)');
  b.resolver({resumo:{total:200}});
  const atual=await nova; assert.strictEqual(atual.atual,true); assert.strictEqual(atual.dados.resumo.total,200);
  a.resolver({resumo:{total:1}}); assert.strictEqual((await antiga).atual,false);
  const c=adiar(), d=adiar(); ctx.c=c;ctx.d=d;
  const falhaAntiga=run('CentralUI.consultar(s, () => c.promise)'), sucessoNovo=run('CentralUI.consultar(s, () => d.promise)');
  d.resolver({}); await sucessoNovo; c.rejeitar(new Error('resposta antiga'));
  assert.strictEqual((await falhaAntiga).atual,false);
  await assert.rejects(run('CentralUI.consultar(s, () => Promise.reject(new Error("Falha de conexão")))'), /Falha de conexão/);
  ctx.Sessao.usuario={id:1}; ctx.sessaoAntiga={usuarioId:1}; const troca=adiar();ctx.troca=troca;
  const respostaAntiga=run('CentralUI.consultar(sessaoAntiga, () => troca.promise)');
  ctx.Sessao.usuario={id:2}; troca.resolver({resumo:{total:9}});
  assert.strictEqual((await respostaAntiga).atual,false, 'Não renderizar resposta de outra sessão');
  const envio=adiar(); ctx.envio=envio; ctx.etapas=etapas;
  const confirmar=run('TarefasUI.confirmarCarteira(() => envio.promise, etapa => etapas.push(etapa))');
  assert.deepStrictEqual(etapas, [], 'Não concluir enquanto a API está pendente');
  envio.resolver({ok:true}); await confirmar; assert.deepStrictEqual(etapas,['concluido']);
  etapas.length=0;
  await assert.rejects(run('TarefasUI.confirmarCarteira(() => Promise.reject(new Error("Prévia expirada")), etapa => etapas.push(etapa))'), /Prévia expirada/);
  assert.deepStrictEqual(etapas, [], 'Erro não pode avançar para concluído');
  console.log('OK - Central UI: filtros, contexto, permissão, consultas concorrentes e confirmação');
})().catch(erro => {console.error(erro);process.exitCode=1;});
'''
    resultado = subprocess.run([node, "-e", script], cwd=raiz, text=True,
                               capture_output=True, encoding="utf-8")
    print(resultado.stdout, end="")
    if resultado.returncode:
        print(resultado.stderr)
    return resultado.returncode


if __name__ == "__main__":
    raise SystemExit(main())
