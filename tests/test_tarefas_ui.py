"""Regras de apresentação da aba 10 (Node opcional, sem DOM ou dependências)."""
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
console.log('OK - tarefas UI: datas civis, regras, competências e revisões da seleção');
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
