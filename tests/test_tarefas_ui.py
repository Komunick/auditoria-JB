"""Regras e contrato de apresentação da aba 10 (Node opcional, sem dependências)."""
import pathlib
import shutil
import subprocess


def main():
    raiz = pathlib.Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        print("PULADO - tarefas UI: Node não instalado")
        return 0
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const ctx = {Abas: {registrar() {}}, console};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('webui/tarefas.js', 'utf8'), ctx);
const run = code => vm.runInContext(code, ctx);
assert.strictEqual(run('TarefasUI.data("2026-02-03")'), '03/02/2026');
assert.strictEqual(run('TarefasUI.data("")'), '—');
assert.strictEqual(run('JSON.stringify(TarefasUI.meses("3, 6, 9, 12"))'), '[3,6,9,12]');
assert.throws(() => run('TarefasUI.meses("3,0,13")'));
assert.throws(() => run('TarefasUI.meses("3,3")'));
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"ultimo_dia_util_mes_seguinte",dia:"20",mes:"4",sem_expediente:"antecipar"}))'), '{"tipo":"ultimo_dia_util_mes_seguinte","sem_expediente":"antecipar"}');
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"dia_mes_fixo",dia:"30",mes:"4",sem_expediente:"adiar"}))'), '{"tipo":"dia_mes_fixo","sem_expediente":"adiar","dia":30,"mes":4}');
assert.strictEqual(run('JSON.stringify(TarefasUI.selecao([{id:1,revision:3},{id:2,revision:1}], new Set([1])))'), '[{"id":1,"revision":3}]');
assert.strictEqual(run('JSON.stringify(TarefasUI.selecao([{id:2,revision:1}], new Set([1])))'), '[]');
assert.strictEqual(run('TarefasUI.rotuloSituacao("concluida")'), 'Concluída');
assert.strictEqual(run('TarefasUI.rotuloSituacao("<script>")'), 'Situação desconhecida');
assert.strictEqual(run('JSON.stringify(TarefasUI.setoresGeridos({setores:[{id:1},{id:2}],setores_geridos:[2]}))'), '[{"id":2}]');
assert.strictEqual(run('JSON.stringify(TarefasUI.usuariosSetor({setores:[{id:2,membros:[1,2]}],usuarios:[{id:1,ativo:1},{id:2,ativo:0},{id:3,ativo:1}]},2))'), '[{"id":1,"ativo":1}]');
assert.strictEqual(run('TarefasUI.podeLote({pode_gerir:true,situacao:"concluida"})'), false);
assert.strictEqual(run('TarefasUI.podeLote({pode_gerir:true,situacao:"em_andamento"})'), true);
assert.strictEqual(run('TarefasUI.podeLote({pode_gerir:false,situacao:"a_fazer"})'), false);
assert.strictEqual(run('TarefasUI.visaoConsulta("configuracao")'), 'cliente');
assert.strictEqual(run('TarefasUI.visaoConsulta("importar")'), 'cliente');
assert.strictEqual(run('TarefasUI.visaoConsulta("minhas")'), 'minhas');
assert.strictEqual(run('JSON.stringify(TarefasUI.ajuste({cliente_id:"1",obrigacao_id:"2",ajuste_tipo:"excluir",valido_de:"",valido_ate:"2026-12-31",motivo:"Teste"},3))'), '{"cliente_id":1,"obrigacao_id":2,"tipo":"excluir","regra_vencimento":null,"valido_de":"","valido_ate":"2026-12-31","motivo":"Teste","revision":3}');
assert.strictEqual(run('TarefasUI.descreverRegra({tipo:"dia_mes_seguinte",dia:20,sem_expediente:"antecipar"})'), 'Dia 20 do mês seguinte à competência; antecipar para dia útil');
assert.strictEqual(run('TarefasUI.descreverRegra({tipo:"ultimo_dia_util_mes_seguinte"})'), 'Último dia útil do mês seguinte à competência');
// Spec 014: representar a regra sem inventar o dia 31 ou prazo ausente.
assert.strictEqual(run('JSON.stringify(TarefasUI.periodos("01-10; 11-20; 21-30"))'), '[{"inicio":1,"fim":10},{"inicio":11,"fim":20},{"inicio":21,"fim":30}]');
assert.strictEqual(run('JSON.stringify(TarefasUI.periodos("01-15\\n16-30"))'), '[{"inicio":1,"fim":15},{"inicio":16,"fim":30}]');
for (const valor of ['', '00-10', '10-32', '15-10', '1-10;10-20', '21-30;1-10', 'dias 1 a 10']) {
  assert.throws(() => run(`TarefasUI.periodos(${JSON.stringify(valor)})`));
}
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"periodos_mes_seguinte",periodos:"01-10;11-20;21-30",dia:"31",sem_expediente:"manter"}))'), '{"tipo":"periodos_mes_seguinte","sem_expediente":"manter","periodos":[{"inicio":1,"fim":10},{"inicio":11,"fim":20},{"inicio":21,"fim":30}]}');
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"sem_vencimento",dia:"20",mes:"4",inicio_dia:"1",sem_expediente:"adiar"}))'), '{"tipo":"sem_vencimento"}');
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"dia_mes_seguinte",dia:"20",inicio_dia:"5",sem_expediente:"antecipar"}))'), '{"tipo":"dia_mes_seguinte","sem_expediente":"antecipar","dia":20,"inicio_dia":5}');
assert.throws(() => run('TarefasUI.regra({tipo:"dia_mes_seguinte",dia:"10",inicio_dia:"20",sem_expediente:"manter"})'));
assert.throws(() => run('TarefasUI.antecedencia({tipo:"dia_mes_seguinte",inicio_dia:"5",inicio_antecedencia_dias:"0"})'));
assert.strictEqual(run('TarefasUI.antecedencia({tipo:"dia_mes_seguinte",inicio_dia:"5",inicio_antecedencia_dias:""})'), null);
assert.strictEqual(run('TarefasUI.antecedencia({tipo:"dia_mes_seguinte",inicio_dia:"",inicio_antecedencia_dias:"7"})'), 7);
assert.strictEqual(run('TarefasUI.antecedencia({tipo:"sem_vencimento",inicio_antecedencia_dias:"7"})'), null);
assert.throws(() => run('TarefasUI.validarPeriodicidade("periodos_mes_seguinte", "anual")'));
assert.strictEqual(run('TarefasUI.validarPeriodicidade("periodos_mes_seguinte", "mensal")'), true);
assert.strictEqual(run('TarefasUI.vencimento("")'), 'Sem vencimento');
assert.strictEqual(run('TarefasUI.vencimento("2026-12-30")'), '30/12/2026');
assert.strictEqual(run('TarefasUI.resultadoPrazo({vencimento:"",fora_do_prazo:false})'), 'Sem vencimento');
assert.strictEqual(run('TarefasUI.resultadoPrazo({vencimento:"2026-10-20",fora_do_prazo:true})'), 'Fora do prazo');
assert.strictEqual(run('TarefasUI.resultadoPrazo({vencimento:"2026-10-20",fora_do_prazo:false})'), 'Dentro do prazo');
assert.strictEqual(run('TarefasUI.descreverRegra({tipo:"sem_vencimento"})'), 'Sem vencimento');
assert.strictEqual(run('TarefasUI.descreverRegra({tipo:"dia_mes_seguinte",dia:20,inicio_dia:5,sem_expediente:"antecipar"})'), 'Início no dia 5; vencimento no dia 20 do mês seguinte à competência; antecipar para dia útil');
assert.strictEqual(run('TarefasUI.descreverRegra({tipo:"periodos_mes_seguinte",periodos:[{inicio:1,fim:15},{inicio:16,fim:30}],sem_expediente:"manter"})'), 'Períodos 01–15 e 16–30 do mês seguinte à competência; manter a data');
assert.strictEqual(run('TarefasUI.ocorrencia({obrigacao_id:7,ocorrencia:2,origem:{intervalo:"11–20"}})'), 'Ocorrência 2 · período 11–20');
assert.strictEqual(run('TarefasUI.ocorrencia({obrigacao_id:7,origem:{}})'), 'Ocorrência 1');
assert.strictEqual(run('TarefasUI.ocorrencia({obrigacao_id:null,origem:{tipo:"avulsa"}})'), '');
assert.strictEqual(run('JSON.stringify(TarefasUI.regra({tipo:"dia_mes_seguinte",dia:"20",inicio_dia:null,sem_expediente:"manter"}))'), '{"tipo":"dia_mes_seguinte","sem_expediente":"manter","dia":20}');
assert.strictEqual(run('JSON.stringify(TarefasUI.camposRegra({tipo:"sem_vencimento"}).filter(c => !c.quando || c.quando({tipo:"sem_vencimento"})).map(c => c.nome))'), '["tipo"]');
assert.strictEqual(run('JSON.stringify(TarefasUI.camposRegra().filter(c => !c.quando || c.quando({tipo:"periodos_mes_seguinte"})).map(c => c.nome))'), '["tipo","periodos","sem_expediente"]');
assert.strictEqual(run('TarefasUI.camposRegra({periodos:[{inicio:1,fim:10},{inicio:11,fim:20},{inicio:21,fim:30}]}).find(c => c.nome === "periodos").valor'), '01-10; 11-20; 21-30');
// DOM mínimo para testar o conteúdo legível e a confirmação da prévia.
const doc = {activeElement: null, listeners: {},
  addEventListener(tipo, fn) { this.listeners[tipo] = fn; },
  removeEventListener(tipo, fn) { if (this.listeners[tipo] === fn) delete this.listeners[tipo]; },
  createElement(tag) {
    return {tagName: tag, children: [], attributes: {}, listeners: {}, textContent: '',
      append(...itens) { for (const item of itens) { this.children.push(item); item.parent = this; } },
      setAttribute(nome, valor) { this.attributes[nome] = valor; },
      addEventListener(tipo, fn) { this.listeners[tipo] = fn; },
      focus() { doc.activeElement = this; },
      remove() { this.parent.children = this.parent.children.filter(e => e !== this); this.parent = null; },
      get isConnected() { return this === doc.body || !!this.parent?.isConnected; }};
  }};
doc.body = doc.createElement('body'); ctx.document = doc;
ctx.previa = {total: 3, itens: [
  {cliente_nome: 'Cliente de teste', titulo: 'Rotina de teste', obrigacao_id: 7, ocorrencia: 1, origem: {intervalo: '01–15'}, inicio: '2026-11-01', vencimento: '2026-11-15'},
  {cliente_nome: 'Cliente de teste', titulo: 'Rotina de teste', obrigacao_id: 7, ocorrencia: 2, origem: {intervalo: '16–30'}, inicio: '2026-11-16', vencimento: '2026-11-30'},
  {cliente_nome: '<b>Cliente de teste</b>', titulo: 'Rotina sem prazo', obrigacao_id: 8, ocorrencia: 1, origem: {}, inicio: '2026-11-01', vencimento: ''}]};
const elementos = e => [e, ...e.children.flatMap(elementos)];
(async () => {
  let resposta = run('TarefasUI.confirmarGeracao(previa, "2026-10")');
  const dialogo = elementos(doc.body).find(e => e.attributes.role === 'dialog');
  assert.strictEqual(dialogo.attributes['aria-label'], 'Prévia de geração');
  const linhas = elementos(dialogo).filter(e => e.tagName === 'tbody')[0].children;
  assert.deepStrictEqual(linhas.map(tr => tr.children.map(td => td.textContent)), [
    ['Cliente de teste', 'Rotina de teste', 'Ocorrência 1 · período 01–15', '01/11/2026', '15/11/2026'],
    ['Cliente de teste', 'Rotina de teste', 'Ocorrência 2 · período 16–30', '16/11/2026', '30/11/2026'],
    ['<b>Cliente de teste</b>', 'Rotina sem prazo', 'Ocorrência 1', '01/11/2026', 'Sem vencimento']]);
  assert.strictEqual(doc.activeElement.textContent, 'Voltar');
  await doc.activeElement.listeners.click();
  assert.strictEqual(await resposta, false);
  assert.strictEqual(doc.body.children.length, 0);
  assert.strictEqual(doc.listeners.keydown, undefined);
  resposta = run('TarefasUI.confirmarGeracao(previa, "2026-10")');
  await elementos(doc.body).find(e => e.textContent === 'Confirmar geração').listeners.click();
  assert.strictEqual(await resposta, true);
  assert.strictEqual(doc.body.children.length, 0);
  console.log('OK - tarefas UI: períodos, início fixo, ausência de prazo, regras, revisão e prévia');
})().catch(erro => { console.error(erro); process.exitCode = 1; });
'''
    result = subprocess.run([node, "-e", script], cwd=raiz, text=True,
                            capture_output=True, encoding="utf-8")
    print(result.stdout, end="")
    if result.returncode:
        print("FALHOU - tarefas UI")
        print(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
