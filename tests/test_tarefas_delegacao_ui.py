"""Consulta e execução delegada de tarefas com DOM e API sintéticos, sem produção."""
from pathlib import Path
import shutil
import subprocess


def main():
    node = shutil.which('node')
    if not node:
        print('PULADO - ações de tarefas UI: Node não instalado')
        return 0
    script = r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const todos=e=>[e,...e.children.flatMap(todos)];
class Elemento {
  constructor(tag='div') {
    this.tagName=tag;this.children=[];this.listeners={};this.attributes={};this.dataset={};
    this.disabled=false;this.checked=false;this._value='';this._text='';
    const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),
      toggle(x,on){if(on)classes.add(x);else classes.delete(x);},contains:x=>classes.has(x)};
  }
  set textContent(v){this._text=String(v);this.children.forEach(x=>x.parent=null);this.children=[];if(this.tagName==='select')this._value='';}
  get textContent(){return this._text;}
  set value(v){const s=String(v);this._value=this.tagName==='select'&&!this.children.some(x=>x.value===s)?'':s;}
  get value(){return this._value;}
  append(...xs){xs.forEach(x=>{x.parent=this;this.children.push(x);});if(this.tagName==='select'&&this.children.length===xs.length)this._value=xs[0]?.value||'';}
  setAttribute(k,v){this.attributes[k]=v;}
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);}
  emitir(k,e={}){return Promise.all((this.listeners[k]||[]).map(fn=>fn({preventDefault(){},target:this,...e})));}
  querySelectorAll(sel){return todos(this).slice(1).filter(e=>sel.split(',').some(s=>{
    const m=/^(\w+)/.exec(s);return m&&e.tagName===m[1]&&(!s.includes(':not(:disabled)')||!e.disabled);
  }));}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null;}
  focus(){documento.activeElement=this;}
  scrollIntoView(){}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null;}
  get isConnected(){return this===documento.body||!!this.parent?.isConnected;}
  getClientRects(){return this.isConnected?[{}]:[];}
}
const documento={listeners:{},activeElement:null,createElement:tag=>new Elemento(tag),getElementById:()=>null,
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},
  removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(x=>x!==fn);},
  emitir(k,detail){return Promise.all((this.listeners[k]||[]).map(fn=>fn({detail})));}};
documento.body=new Elemento('body');
const nos={},nav=['minhas','setor','cliente','configuracao','importar'].map(visao=>{
  const b=new Elemento('button');b.dataset.visao=visao;b.closest=()=>b;return b;
});
const container=new Elemento();documento.body.append(container);
Object.defineProperty(container,'innerHTML',{set(html){
  for(const [,tag,id] of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)){nos[id]=new Elemento(tag);container.append(nos[id]);}
  nos['tar-nav'].querySelectorAll=()=>nav;
  nos['tar-nav'].querySelector=sel=>nav.find(b=>sel.includes('"'+b.dataset.visao+'"'));
  nos['tar-tabela'].body=new Elemento('tbody');nos['tar-tabela'].append(nos['tar-tabela'].body);
  nos['tar-tabela'].querySelector=()=>nos['tar-tabela'].body;
  nos['tar-filtros'].reset=()=>{};
}});
container.querySelector=s=>nos[s.slice(1)];
let montar, erroMutacao=null, adiarDetalhe=null;
const chamadas=[],avisos=[], catalogo={clientes:[{id:1,nome:'Cliente fictício'}],
  setores:[{id:2,nome:'Fiscal fictício',membros:[1,3]}],usuarios:[{id:1,nome:'Titular fictício',ativo:1},{id:3,nome:'Colega fictício',ativo:1}],
  obrigacoes:[],caracteristicas:[],setores_geridos:[],setores_consultaveis:[2]};
let tarefa={id:7,titulo:'Obrigação fictícia',cliente_id:1,cliente_nome:'Cliente fictício',setor_id:2,setor_nome:'Fiscal fictício',
  situacao:'a_fazer',revision:3,inicio:'2026-12-01',vencimento:'2026-12-20',competencia:'2026-11',
  responsavel_usuario_id:1,responsavel_efetivo_id:1,obrigacao_id:5,origem:{regra:{tipo:'dia_mes_seguinte',dia:20}},
  pode_gerir:false,pode_executar:false,pode_reativar:false,pode_alterar_vencimento:false,eventos:[],
  execucao:{pode_autorizar:false,pode_solicitar:true,candidatos:[],registros:[]}};
const copia=x=>JSON.parse(JSON.stringify(x));
const api=async(url,op={})=>{
  chamadas.push({url,...copia(op)});
  if(url==='/api/tarefas/catalogo')return copia(catalogo);
  if(url.startsWith('/api/tarefas/opcoes-filtros?'))return {titulos:[],total_escopo:1};
  if(url.startsWith('/api/tarefas?'))return {itens:[copia(tarefa)],pagina:1,paginas:1,total:1};
  if(url==='/api/tarefas/7')return adiarDetalhe?adiarDetalhe.promise:copia(tarefa);
  if(op.json){
    if(erroMutacao)throw erroMutacao;
    if(op.json.revision!==tarefa.revision)throw new Error('O registro mudou. Recarregue antes de salvar.');
    if(url.endsWith('/execucao/solicitar')){
      tarefa.execucao.pode_solicitar=false;
      tarefa.execucao.registros.push({id:8,executor_usuario_id:3,executor_nome:'Colega fictício',solicitante_nome:'Colega fictício',estado:'pendente',vigente:true,motivo:op.json.motivo,criada_em:'2026-11-04T12:00:00Z'});
    }else if(url.endsWith('/execucao/autorizar')){
      tarefa.execucao.registros=[{id:8,executor_usuario_id:3,executor_nome:'Colega fictício',solicitante_nome:'Titular fictício',decidido_nome:'Titular fictício',estado:'autorizada',vigente:true,pode_revogar:true,motivo:op.json.motivo,decisao_motivo:op.json.motivo,criada_em:'2026-11-04T12:00:00Z',decidida_em:'2026-11-04T12:00:00Z'}];
    }else if(url.endsWith('/decidir')){
      const r=tarefa.execucao.registros.find(r=>r.id===8);r.estado={aprovar:'autorizada',recusar:'recusada',revogar:'revogada'}[op.json.acao];
      r.decisao_motivo=op.json.motivo;r.pode_aprovar=false;r.pode_recusar=false;r.pode_revogar=op.json.acao==='aprovar';
    }else throw new Error('Mutação inesperada: '+url);
    tarefa.revision++;return copia(tarefa);
  }
  return {};
};
const ctx={console,URLSearchParams,document:documento,api,toast:(...args)=>avisos.push(args),
  Sessao:{usuario:{id:3},pode:p=>['aba.tarefas','tarefas.executar','tarefas.consultar_setor'].includes(p),ehAdmin:()=>false},Abas:{registrar(n,fn){montar=fn;}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/tarefas.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx);
const esperar=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const texto=e=>todos(e).map(x=>x.textContent).join(' ');
const botao=(e,nome)=>todos(e).find(x=>x.tagName==='button'&&x.textContent===nome);
const dialogo=()=>todos(documento.body).find(e=>e.attributes.role==='dialog');
const campo=(d,nome)=>todos(d).find(e=>e.name===nome);
const mutacoes=()=>chamadas.filter(c=>c.json);
const abrir=async()=>{await documento.emitir('tarefas:abrir',{filtros:{visao:'setor'},tarefa_id:7});await esperar();};
const adiar=()=>{let resolver;const promise=new Promise(r=>resolver=r);return {promise,resolver};};
(async()=>{
  montar(container);await esperar();
  assert(!nav.find(b=>b.dataset.visao==='setor').classList.contains('oculto'),'Membro consultante vê Setor sem ganhar gestão');
  assert(!botao(nos['tar-lote'],'Redistribuir'));assert(!botao(nos['tar-acoes'],'Gerar competência'));
  assert.match(nos['tar-escopo'].textContent,/autorizad/);
  await abrir();
  assert(botao(nos['tar-detalhe'],'Solicitar execução'));
  for(const acao of ['Em andamento','Concluída','Comentar','Dispensar','Autorizar execução','Alterar vencimento'])assert(!botao(nos['tar-detalhe'],acao),acao);
  await botao(nos['tar-detalhe'],'Solicitar execução').emitir('click');let d=dialogo();
  assert.match(texto(d),/aprova/);assert.match(texto(d),/somente esta tarefa/);
  assert.strictEqual(campo(d,'motivo').required,true);assert.strictEqual(campo(d,'motivo').maxLength,4000);
  await botao(d,'Cancelar').emitir('click');assert.strictEqual(mutacoes().length,0);
  await botao(nos['tar-detalhe'],'Solicitar execução').emitir('click');d=dialogo();campo(d,'motivo').value='Posso ajudar nesta entrega';
  await d.emitir('submit');assert(!dialogo());
  assert.deepStrictEqual(mutacoes().at(-1),{url:'/api/tarefas/7/execucao/solicitar',json:{revision:3,motivo:'Posso ajudar nesta entrega'}});
  assert.match(texto(nos['tar-detalhe']),/Aguardando aprovação/);
  assert(!botao(nos['tar-detalhe'],'Em andamento'));assert(!botao(nos['tar-detalhe'],'Solicitar execução'));
  // Troca de DTO para responsável (mesma sessão sintética): capacidades vêm do servidor.
  tarefa.execucao={pode_autorizar:true,pode_solicitar:false,candidatos:[{id:3,nome:'Colega fictício'}],
    registros:tarefa.execucao.registros.map(r=>({...r,pode_aprovar:true,pode_recusar:true}))};
  await abrir();assert(botao(nos['tar-detalhe'],'Aprovar'));assert(botao(nos['tar-detalhe'],'Recusar'));
  await botao(nos['tar-detalhe'],'Aprovar').emitir('click');d=dialogo();campo(d,'motivo').value='<img src=x onerror=alert(1)> teste literal';
  erroMutacao=new Error('O registro mudou. Recarregue antes de salvar.');await d.emitir('submit');
  assert.strictEqual(dialogo(),d);assert.match(texto(d),/Recarregue/);assert.strictEqual(botao(d,'Salvar').disabled,false);
  erroMutacao=null;await d.emitir('submit');assert(!dialogo());
  assert.deepStrictEqual(mutacoes().at(-1),{url:'/api/tarefas/7/execucao/8/decidir',json:{acao:'aprovar',revision:4,motivo:'<img src=x onerror=alert(1)> teste literal'}});
  assert.match(texto(nos['tar-detalhe']),/Autorizada/);assert.match(texto(nos['tar-detalhe']),/<img src=x onerror=alert\(1\)> teste literal/);
  assert(!todos(nos['tar-detalhe']).some(e=>e.tagName==='img'));
  await botao(nos['tar-detalhe'],'Revogar').emitir('click');d=dialogo();campo(d,'motivo').value='Responsável reassume';await d.emitir('submit');
  assert.strictEqual(mutacoes().at(-1).json.acao,'revogar');assert.strictEqual(mutacoes().at(-1).json.revision,5);
  assert.match(texto(nos['tar-detalhe']),/Revogada/);
  tarefa.execucao.registros=[{id:8,executor_nome:'Colega fictício',estado:'pendente',vigente:true,pode_recusar:true,pode_aprovar:true}];await abrir();
  await botao(nos['tar-detalhe'],'Recusar').emitir('click');d=dialogo();campo(d,'motivo').value='Responsável executará';await d.emitir('submit');
  assert.strictEqual(mutacoes().at(-1).json.acao,'recusar');assert.match(texto(nos['tar-detalhe']),/Recusada/);
  assert(!botao(nos['tar-detalhe'],'Em andamento'));
  tarefa.eventos.push({tipo:'execucao',de:'pendente',para:'recusada',comentario:'Pessoa fictícia · motivo de teste',usuario_login:'titular.demo',criado_em:'2026-11-04T12:00:00Z'});
  await abrir();assert.match(texto(nos['tar-detalhe']),/Execução: Aguardando aprovação → Recusada/);
  await botao(nos['tar-detalhe'],'Autorizar execução').emitir('click');d=dialogo();
  assert.strictEqual(campo(d,'usuario_id').tagName,'select');assert.strictEqual(campo(d,'usuario_id').children.length,2);
  campo(d,'usuario_id').value='3';campo(d,'motivo').value='Apoio pontual';await d.emitir('submit');
  assert.deepStrictEqual(mutacoes().at(-1),{url:'/api/tarefas/7/execucao/autorizar',json:{usuario_id:3,revision:7,motivo:'Apoio pontual'}});
  assert.match(texto(nos['tar-detalhe']),/Registrado por Titular fictício/);
  assert.strictEqual(todos(nos['tar-detalhe']).filter(e=>e.tagName==='p'&&e.textContent==='Apoio pontual').length,1,'Concessão direta exibe motivo idêntico apenas uma vez');
  // Autorização dá execução; nenhuma ação de gestão.
  tarefa.execucao={pode_autorizar:false,pode_solicitar:false,candidatos:[],registros:[{id:8,executor_nome:'Colega fictício',estado:'autorizada',vigente:true}]};
  tarefa.execucao_delegada=true;tarefa.pode_executar=true;await abrir();
  assert(botao(nos['tar-detalhe'],'Em andamento'));assert(botao(nos['tar-detalhe'],'Comentar'));
  for(const acao of ['Dispensar','Alterar vencimento','Reativar tarefa','Autorizar execução','Conferida'])assert(!botao(nos['tar-detalhe'],acao));
  assert.match(texto(nos['tar-tabela']),/Execução autorizada/);assert.match(texto(nos['tar-detalhe']),/responsável/);
  tarefa.execucao_delegada=false;tarefa.pode_executar=false;tarefa.execucao.registros[0].vigente=false;await abrir();
  assert.match(texto(nos['tar-detalhe']),/Sem validade atual/);assert(!botao(nos['tar-detalhe'],'Em andamento'));
  tarefa.execucao={};await abrir();
  for(const acao of ['Solicitar execução','Autorizar execução','Aprovar','Recusar','Revogar'])assert(!botao(nos['tar-detalhe'],acao),'DTO sem capacidade não concede '+acao);
  // Revogar consulta remove a aba no próximo catálogo sem conceder gestão.
  catalogo.setores_consultaveis=[];await nos['tar-atualizar'].emitir('click');await esperar();
  assert(nav.find(b=>b.dataset.visao==='setor').classList.contains('oculto'));
  catalogo.setores_consultaveis=[2];tarefa.execucao.pode_solicitar=true;await abrir();
  await botao(nos['tar-detalhe'],'Solicitar execução').emitir('click');d=dialogo();campo(d,'motivo').value='Sessão anterior';
  const antes=mutacoes().length;ctx.Sessao.usuario={id:9};await d.emitir('submit');
  assert.strictEqual(mutacoes().length,antes);assert.match(texto(d),/sessão/);await botao(d,'Cancelar').emitir('click');ctx.Sessao.usuario={id:3};
  // Resposta de detalhe da sessão anterior é descartada.
  adiarDetalhe=adiar();const antiga=abrir();await esperar();ctx.Sessao.usuario=null;await documento.emitir('sessao:encerrada');
  adiarDetalhe.resolver({...tarefa,titulo:'Não mostrar sessão anterior'});await antiga;
  assert(!texto(nos['tar-detalhe']).includes('Não mostrar sessão anterior'));
  console.log('OK - consulta de setor e delegação UI: solicitar, autorizar, aprovar, revogar, permissões, conflito, sessão e texto seguro');
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
