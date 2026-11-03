"""Eventos reais dos filtros com DOM/API sintéticos, sem acesso à produção."""
from pathlib import Path
import shutil
import subprocess


def main():
    node = shutil.which('node')
    if not node:
        print('PULADO - filtros UI: Node não instalado')
        return 0
    script = r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
class Elemento {
  constructor(tag='div') {
    this.tagName=tag; this.children=[]; this.listeners={}; this.attributes={};
    this.dataset={}; this.disabled=false; this.checked=false; this._value=''; this._text='';
    const classes=new Set(); this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),
      toggle(x,on) {if(on) classes.add(x);else classes.delete(x);},contains:x=>classes.has(x)};
  }
  set textContent(v) {this._text=String(v);this.children=[];if(this.tagName==='select') this._value='';}
  get textContent() {return this._text;}
  set value(v) {const s=String(v);this._value=this.tagName==='select'&&!this.children.some(x=>x.value===s)?'':s;}
  get value() {return this._value;}
  append(...xs) {this.children.push(...xs);if(this.tagName==='select'&&this.children.length===xs.length) this._value=xs[0]?.value||'';}
  setAttribute(k,v) {this.attributes[k]=v;}
  addEventListener(k,fn) {(this.listeners[k]||=[]).push(fn);}
  emitir(k,e={}) {return Promise.all((this.listeners[k]||[]).map(fn=>fn({preventDefault(){},target:this,...e})));}
  querySelectorAll() {return [];}
  querySelector() {return new Elemento();}
}
const nos={},nav=['minhas','setor','cliente','configuracao','importar'].map(visao=>{
  const b=new Elemento('button');b.dataset.visao=visao;b.closest=()=>b;return b;
});
const documento={listeners:{},createElement:tag=>new Elemento(tag),getElementById:()=>null,
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},
  emitir(k,detail){return Promise.all((this.listeners[k]||[]).map(fn=>fn({detail})));}};
const container=new Elemento();
Object.defineProperty(container,'innerHTML',{set(html){
  for(const [,tag,id] of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)) nos[id]=new Elemento(tag);
  nos['tar-nav'].querySelectorAll=()=>nav;
  nos['tar-nav'].querySelector=sel=>nav.find(b=>sel.includes('"'+b.dataset.visao+'"'));
  nos['tar-tabela'].body=new Elemento('tbody');
  nos['tar-tabela'].querySelector=()=>nos['tar-tabela'].body;
  nos['tar-filtros'].reset=()=>{
    for(const id of ['titulo','texto','cliente','setor','responsavel','competencia','situacao','de','ate'])
      if(nos['tar-'+id]) nos['tar-'+id].value='';
    nos['tar-fila'].value='todas';
    for(const id of ['sem-responsavel','abertas','pendente-conferencia']) nos['tar-'+id].checked=false;
  };
}});
container.querySelector=s=>nos[s.slice(1)];
let montar;
const chamadas=[], catalogo={clientes:[{id:1,nome:'Cliente sintético'}],setores:[{id:2,nome:'Fiscal',membros:[1,3]}],
  usuarios:[{id:1,nome:'Admin sintético',ativo:1},{id:3,nome:'Pessoa sintética',ativo:1}],
  obrigacoes:[],caracteristicas:[],setores_geridos:[2]};
let total=1;
const resposta=()=>({itens:[],pagina:1,paginas:1,total});
const api=async url=>{
  chamadas.push(url);
  if(url==='/api/tarefas/catalogo') return catalogo;
  if(url.startsWith('/api/tarefas/opcoes-filtros?')) return {titulos:['ISS','ISS complementar','Avulsa <teste>'],total_escopo:3};
  if(url.startsWith('/api/tarefas?')) return resposta();
  return {};
};
const ctx={console,URLSearchParams,document:documento,api,toast(){},
  Sessao:{usuario:{id:1},pode:()=>true,ehAdmin:()=>true},Abas:{registrar(n,fn){montar=fn;}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/tarefas.js','utf8'),ctx);
const esperar=async()=>{for(let i=0;i<30;i++) await Promise.resolve();};
const ultima=()=>new URLSearchParams(chamadas.filter(x=>x.startsWith('/api/tarefas?')).at(-1).split('?')[1]);
const adiar=()=>{let resolver;return {promise:new Promise(r=>resolver=r),resolver:v=>resolver(v)};};
(async()=>{
  montar(container);await esperar();
  assert.strictEqual(nos['tar-titulo']?.tagName,'select','Tarefa deve ser selecionável sem digitar');
  assert.deepStrictEqual(nos['tar-titulo'].children.map(o=>o.textContent),['Todas as tarefas','ISS','ISS complementar','Avulsa <teste>']);
  assert.match(nos['tar-escopo'].textContent,/atribuídas a você/);
  nos['tar-titulo'].value='ISS';nos['tar-cliente'].value='1';nos['tar-competencia'].value='2026-10';
  nos['tar-de'].value='2026-11-01';nos['tar-ate'].value='2026-11-30';nos['tar-abertas'].checked=true;
  await nos['tar-filtros'].emitir('submit');await esperar();
  for(const [k,v] of Object.entries({visao:'minhas',titulo:'ISS',cliente_id:'1',competencia:'2026-10',vencimento_de:'2026-11-01',vencimento_ate:'2026-11-30',abertas:'true',pagina:'1'})) assert.strictEqual(ultima().get(k),v,k);
  assert.strictEqual(nos['tar-titulo'].children.length,4,'Lista não encolhe com a página/filtros');
  total=0;await nos['tar-filtros'].emitir('submit');await esperar();
  assert.match(nos['tar-tabela'].body.children[0].children[0].textContent,/combinação de filtros/);
  nos['tar-fila'].value='sem_responsavel';let antes=chamadas.length;
  await nos['tar-filtros'].emitir('submit');await esperar();
  assert.strictEqual(chamadas.length,antes,'Filtro impossível não deve enviar consulta');
  assert.match(nos['tar-status'].textContent,/Minhas tarefas/);
  await nos['tar-limpar'].emitir('click');await esperar();
  assert.deepStrictEqual([...ultima().entries()],[['visao','minhas'],['fila','todas'],['pagina','1']]);
  assert.strictEqual(nos['tar-titulo'].value,'');assert.strictEqual(nos['tar-abertas'].checked,false);
  await nos['tar-nav'].emitir('click',{target:nav.find(b=>b.dataset.visao==='cliente')});await esperar();
  nos['tar-responsavel'].value='3';nos['tar-sem-responsavel'].checked=true;antes=chamadas.length;
  await nos['tar-filtros'].emitir('submit');await esperar();
  assert.strictEqual(chamadas.length,antes);assert.match(nos['tar-status'].textContent,/responsável/i);
  await nos['tar-limpar'].emitir('click');await esperar();
  nos['tar-de'].value='2026-11-30';nos['tar-ate'].value='2026-11-01';antes=chamadas.length;
  await nos['tar-filtros'].emitir('submit');await esperar();
  assert.strictEqual(chamadas.length,antes);assert.match(nos['tar-status'].textContent,/data inicial/i);
  await nos['tar-limpar'].emitir('click');await esperar();
  await documento.emitir('tarefas:abrir',{filtros:{visao:'cliente',texto:'Recebida da Central'},fila:'atrasadas'});await esperar();
  assert.strictEqual(ultima().get('texto'),'Recebida da Central');assert.strictEqual(ultima().get('fila'),'atrasadas');
  assert.strictEqual(nos['tar-texto'].value,'Recebida da Central','Busca recebida permanece visível');
  // Resposta atrasada de opções não altera a visão atual nem dispara listagem antiga.
  const antigo=adiar();ctx.api=url=>url.startsWith('/api/tarefas/opcoes-filtros?')?antigo.promise:api(url);
  nos['tar-atualizar'].emitir('click');await esperar();ctx.api=api;
  await nos['tar-limpar'].emitir('click');await esperar();antes=chamadas.length;
  antigo.resolver({titulos:['Obsoleto'],total_escopo:1});await esperar();
  assert.strictEqual(chamadas.length,antes);assert.strictEqual(nos['tar-titulo'].children.some(o=>o.value==='Obsoleto'),false);
  const edicao=adiar();ctx.api=url=>url.startsWith('/api/tarefas/opcoes-filtros?')?edicao.promise:api(url);
  nos['tar-titulo'].value='ISS';nos['tar-filtros'].emitir('submit');
  nos['tar-titulo'].value='ISS complementar';
  edicao.resolver({titulos:['ISS','ISS complementar'],total_escopo:2});await esperar();
  assert.strictEqual(nos['tar-titulo'].value,'ISS complementar','Resposta não deve desfazer uma edição feita durante a consulta');
  assert.strictEqual(ultima().get('titulo'),'ISS','A consulta mantém os filtros submetidos');
  // Encerrar sessão invalida opções e resultados em andamento.
  const logout=adiar();ctx.api=()=>logout.promise;nos['tar-filtros'].emitir('submit');
  await documento.emitir('sessao:encerrada');ctx.Sessao.usuario=null;
  logout.resolver({titulos:['Sessão anterior'],total_escopo:1});await esperar();
  assert.strictEqual(nos['tar-titulo'].children.some(o=>o.value==='Sessão anterior'),false);
  console.log('OK - filtros UI: opções, combinação, conflitos, limpar, Central e concorrência');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    resultado = subprocess.run([node, '-e', script], cwd=Path(__file__).resolve().parents[1],
                               text=True, capture_output=True, encoding='utf-8')
    print(resultado.stdout, end='')
    if resultado.returncode:
        print(resultado.stderr)
    return resultado.returncode


if __name__ == '__main__':
    raise SystemExit(main())
