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
  // DOM sintético: exercita os eventos reais da Central e as opções renderizadas.
  class Elemento {
    constructor(tag='div') { this.tagName=tag; this.children=[]; this.listeners={}; this.attributes={}; this.dataset={}; this.disabled=false; this.isConnected=true; this._value=''; this._text=''; this.classList={add() {},remove() {},toggle() {}}; }
    set textContent(v) { this._text=String(v); this.children=[]; if(this.tagName==='select') this._value=''; }
    get textContent() { return this._text; }
    set value(v) { const valor=String(v); this._value=this.tagName==='select' && !this.children.some(e=>e.value===valor) ? '' : valor; }
    get value() { return this._value; }
    append(...itens) { this.children.push(...itens); if(this.tagName==='select' && this.children.length===itens.length) this._value=itens[0]?.value || ''; }
    setAttribute(k,v) { this.attributes[k]=v; }
    addEventListener(k,fn) { (this.listeners[k] ||= []).push(fn); }
    emitir(k) { return Promise.all((this.listeners[k] || []).map(fn=>fn({preventDefault() {}}))); }
    querySelector() { return null; }
    focus() {}
  }
  const nos={}, controles={}, documento={listeners:{},createElement:tag=>new Elemento(tag),
    addEventListener(k,fn) { (this.listeners[k] ||= []).push(fn); },
    emitir(k) { return Promise.all((this.listeners[k] || []).map(fn=>fn())); }};
  const container=new Elemento();
  Object.defineProperty(container,'innerHTML',{set(html) {
    for(const [,id] of html.matchAll(/id="([^"]+)"/g)) nos[id]=new Elemento(id==='central-fila'?'select':'div');
    for(const nome of ['visao','cliente_id','setor_id','responsavel_usuario_id','competencia','texto']) controles[nome]=new Elemento(['competencia','texto'].includes(nome)?'input':'select');
    const op=(valor)=>{const e=new Elemento('option');e.value=valor;return e;};
    controles.visao.append(op('cliente'),op('minhas'));
    const form=nos['central-filtros']; form.elements={namedItem:n=>controles[n]}; form.querySelectorAll=()=>Object.values(controles); form.reset=()=>{};
  }});
  container.querySelector=seletor=>nos[seletor.slice(1)]; ctx.document=documento;ctx.container=container;
  ctx.Sessao.usuario={id:1}; ctx.Sessao.pode=p=>p==='aba.tarefas';
  let catalogo={clientes:[{id:1,nome:'Cliente sintético A'}],setores:[{id:3,nome:'Setor sintético'}],usuarios:[{id:4,nome:'Pessoa sintética',ativo:1}],setores_geridos:[3]};
  const chamadas=[];
  const painel={hoje:'2026-10-28',alerta_dias:7,resumo:{total:0,pendentes:0},fila:{itens:[],pagina:1,paginas:0,total:0},por_responsavel:[]};
  ctx.api=async url=>{chamadas.push(url);return url==='/api/tarefas/catalogo'?catalogo:painel;};
  const esperar=async()=>{for(let i=0;i<20;i++) await Promise.resolve();};
  assert.strictEqual(run('CentralUI.montar(container)'),true); await esperar();
  assert.deepStrictEqual(chamadas.map(u=>u.split('?')[0]),['/api/tarefas/catalogo','/api/tarefas/painel']);
  controles.visao.value='setor';controles.cliente_id.value='1';controles.setor_id.value='3';controles.responsavel_usuario_id.value='4';controles.competencia.value='2026-10';controles.texto.value='teste';
  await nos['central-filtros'].emitir('submit');await esperar();
  catalogo={...catalogo,clientes:[...catalogo.clientes,{id:2,nome:'Cliente sintético B'}]};chamadas.length=0;
  await documento.emitir('inicio:abrir');await esperar();
  assert.deepStrictEqual(chamadas.map(u=>u.split('?')[0]),['/api/tarefas/catalogo','/api/tarefas/painel'],'Reabrir deve atualizar catálogo antes do painel');
  assert.strictEqual(controles.cliente_id.children.some(o=>o.value==='2'),true,'Novo cliente aparece sem reload');
  assert.strictEqual(controles.cliente_id.value,'1','Preserva cliente ainda válido');
  let consulta=new URLSearchParams(chamadas.at(-1).split('?')[1]);
  for(const [k,v] of Object.entries({visao:'setor',cliente_id:'1',setor_id:'3',responsavel_usuario_id:'4',competencia:'2026-10',texto:'teste'})) assert.strictEqual(consulta.get(k),v);
  assert.strictEqual(controles.visao.children.filter(o=>o.value==='setor').length,1,'Reabrir não duplica a opção de escopo');
  catalogo={...catalogo,clientes:[{id:2,nome:'Cliente sintético B'},{id:5,nome:'Cliente sintético C'}],usuarios:[],setores_geridos:[]};chamadas.length=0;
  await nos['central-atualizar'].emitir('click');await esperar();
  assert.deepStrictEqual(chamadas.map(u=>u.split('?')[0]),['/api/tarefas/catalogo','/api/tarefas/painel'],'Atualizar deve refazer catálogo antes do painel');
  assert.strictEqual(controles.cliente_id.children.some(o=>o.value==='5'),true);
  assert.strictEqual(controles.cliente_id.value,'');assert.strictEqual(controles.responsavel_usuario_id.value,'');
  consulta=new URLSearchParams(chamadas.at(-1).split('?')[1]);
  assert.strictEqual(consulta.has('cliente_id'),false);assert.strictEqual(consulta.has('responsavel_usuario_id'),false);
  assert.strictEqual(consulta.get('setor_id'),'3');assert.strictEqual(consulta.get('competencia'),'2026-10');assert.strictEqual(consulta.get('texto'),'teste');
  assert.strictEqual(consulta.get('visao'),'cliente');assert.strictEqual(controles.visao.value,'cliente');
  assert.strictEqual(controles.visao.children.filter(o=>o.value==='setor').length,0,'Escopo sem permissão não permanece nas opções');
  const velho=adiar(),novo=adiar();let pendentes=[velho,novo];chamadas.length=0;
  ctx.api=url=>{chamadas.push(url);return url==='/api/tarefas/catalogo'?pendentes.shift().promise:Promise.resolve(painel);};
  documento.emitir('inicio:abrir');documento.emitir('inicio:abrir');
  novo.resolver(catalogo);await esperar();velho.resolver({...catalogo,clientes:[{id:99,nome:'Resposta obsoleta'}]});await esperar();
  assert.strictEqual(controles.cliente_id.children.some(o=>o.value==='99'),false,'Catálogo antigo não sobrescreve o atual');
  assert.strictEqual(chamadas.filter(u=>u.startsWith('/api/tarefas/painel')).length,1);
  const anterior=adiar();ctx.api=()=>anterior.promise;documento.emitir('inicio:abrir');
  documento.emitir('sessao:encerrada');anterior.resolver({...catalogo,clientes:[{id:98,nome:'Sessão encerrada'}]});await esperar();
  assert.strictEqual(controles.cliente_id.children.some(o=>o.value==='98'),false,'Encerrar sessão invalida também catálogo pendente');
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
