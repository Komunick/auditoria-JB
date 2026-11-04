"""Ações individuais de tarefas com DOM e API sintéticos, sem produção."""
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
let montar, erroMutacao=null;
const chamadas=[],avisos=[], catalogo={clientes:[{id:1,nome:'Cliente fictício'}],
  setores:[{id:2,nome:'Fiscal fictício',membros:[1,3]}],usuarios:[{id:1,nome:'Gestão fictícia',ativo:1}],
  obrigacoes:[],caracteristicas:[],setores_geridos:[2]};
let tarefa={id:7,titulo:'Obrigação fictícia',cliente_id:1,cliente_nome:'Cliente fictício',setor_id:2,setor_nome:'Fiscal fictício',
  situacao:'dispensada',revision:3,inicio:'2026-12-01',vencimento:'2026-12-20',competencia:'2026-11',
  responsavel_usuario_id:3,obrigacao_id:5,origem:{regra:{tipo:'dia_mes_seguinte',dia:20}},
  pode_gerir:true,pode_executar:false,pode_reativar:true,pode_alterar_vencimento:false,eventos:[]};
const copia=x=>JSON.parse(JSON.stringify(x));
const api=async(url,op={})=>{
  chamadas.push({url,...copia(op)});
  if(url==='/api/tarefas/catalogo')return copia(catalogo);
  if(url.startsWith('/api/tarefas/opcoes-filtros?'))return {titulos:[],total_escopo:1};
  if(url.startsWith('/api/tarefas?'))return {itens:[],pagina:1,paginas:1,total:1};
  if(url==='/api/tarefas/7')return copia(tarefa);
  if(op.json){
    if(erroMutacao)throw erroMutacao;
    if(op.json.revision!==tarefa.revision)throw new Error('O registro mudou. Recarregue antes de salvar.');
    if(url.endsWith('/situacao')){
      tarefa.situacao='a_fazer';tarefa.pode_reativar=false;tarefa.pode_alterar_vencimento=true;
      tarefa.eventos.push({tipo:'situacao',de:'dispensada',para:'a_fazer',comentario:op.json.motivo||op.json.comentario,criado_em:'2026-11-04T12:00:00Z'});
    }else if(url.endsWith('/vencimento')){
      tarefa.eventos.push({tipo:'vencimento',de:tarefa.vencimento,para:op.json.vencimento,comentario:op.json.motivo,criado_em:'2026-11-04T12:00:00Z'});
      tarefa.vencimento=op.json.vencimento;
    }else throw new Error('Mutação inesperada: '+url);
    tarefa.revision++;return copia(tarefa);
  }
  return {};
};
const ctx={console,URLSearchParams,document:documento,api,toast:(...args)=>avisos.push(args),
  Sessao:{usuario:{id:1},pode:()=>true,ehAdmin:()=>true},Abas:{registrar(n,fn){montar=fn;}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/tarefas.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx);
const esperar=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
const texto=e=>todos(e).map(x=>x.textContent).join(' ');
const botao=(e,nome)=>todos(e).find(x=>x.tagName==='button'&&x.textContent===nome);
const dialogo=()=>todos(documento.body).find(e=>e.attributes.role==='dialog');
const campo=(d,nome)=>todos(d).find(e=>e.name===nome);
const mutacoes=()=>chamadas.filter(c=>c.json);
const abrir=async()=>{await documento.emitir('tarefas:abrir',{filtros:{visao:'setor'},tarefa_id:7});await esperar();};
(async()=>{
  montar(container);await esperar();await abrir();
  const reativar=botao(nos['tar-detalhe'],'Reativar tarefa');
  assert(reativar,'Gestor deve poder reativar a tarefa dispensada');
  assert(!botao(nos['tar-detalhe'],'Alterar vencimento'),'Dispensada precisa ser reativada antes de editar o prazo');
  await reativar.emitir('click');let d=dialogo();
  assert.match(texto(d),/A fazer/);assert.match(texto(d),/mesma tarefa/);
  assert.strictEqual(campo(d,'motivo').required,true);assert.strictEqual(campo(d,'motivo').maxLength,4000);
  await botao(d,'Cancelar').emitir('click');assert(!dialogo());assert.strictEqual(mutacoes().length,0);
  await reativar.emitir('click');d=dialogo();campo(d,'motivo').value='Dispensa de teste incorreta';
  erroMutacao=new Error('O registro mudou. Recarregue antes de salvar.');
  await d.emitir('submit');assert.strictEqual(dialogo(),d);assert.match(texto(d),/Recarregue/);
  assert.strictEqual(tarefa.situacao,'dispensada');assert.strictEqual(botao(d,'Salvar').disabled,false);
  erroMutacao=null;await d.emitir('submit');assert(!dialogo());
  assert.deepStrictEqual(mutacoes().at(-1),{url:'/api/tarefas/7/situacao',json:{situacao:'a_fazer',revision:3,motivo:'Dispensa de teste incorreta'}});
  assert.match(texto(nos['tar-detalhe']),/Dispensada → A fazer/);
  assert(!botao(nos['tar-detalhe'],'Reativar tarefa'));
  await botao(nos['tar-detalhe'],'Alterar vencimento').emitir('click');d=dialogo();
  assert.strictEqual(campo(d,'vencimento').type,'date');assert.strictEqual(campo(d,'vencimento').value,'2026-12-20');
  assert.strictEqual(campo(d,'vencimento').min,'2026-12-01');assert.strictEqual(campo(d,'vencimento').required,true);
  assert.strictEqual(campo(d,'motivo').required,true);assert.strictEqual(campo(d,'motivo').maxLength,4000);
  assert.match(texto(d),/somente esta tarefa/);assert.match(texto(d),/próximas gerações/);
  const antes=mutacoes().length;await botao(d,'Cancelar').emitir('click');assert.strictEqual(mutacoes().length,antes);
  await botao(nos['tar-detalhe'],'Alterar vencimento').emitir('click');d=dialogo();
  campo(d,'vencimento').value='2026-12-22';campo(d,'motivo').value='<img src=x onerror=alert(1)> exemplo literal';
  erroMutacao=new Error('Informe um novo vencimento válido.');await d.emitir('submit');
  assert.strictEqual(dialogo(),d);assert.match(texto(d),/vencimento válido/);assert.strictEqual(tarefa.vencimento,'2026-12-20');
  erroMutacao=null;await d.emitir('submit');assert(!dialogo());
  assert.deepStrictEqual(mutacoes().at(-1),{url:'/api/tarefas/7/vencimento',json:{vencimento:'2026-12-22',revision:4,motivo:'<img src=x onerror=alert(1)> exemplo literal'}});
  assert.match(texto(nos['tar-detalhe']),/20\/12\/2026 → 22\/12\/2026/);
  assert.match(texto(nos['tar-detalhe']),/<img src=x onerror=alert\(1\)> exemplo literal/);
  assert.strictEqual(todos(nos['tar-detalhe']).some(e=>e.tagName==='img'),false);
  await botao(nos['tar-detalhe'],'Alterar vencimento').emitir('click');d=dialogo();
  campo(d,'vencimento').value='2026-12-23';campo(d,'motivo').value='Versão atual';await d.emitir('submit');
  assert.strictEqual(mutacoes().at(-1).json.revision,5,'Segundo envio usa a revisão recarregada');
  tarefa.eventos.push({tipo:'vencimento',de:'',para:'2026-12-25',comentario:'Prazo explícito',criado_em:'2026-11-04T12:00:00Z'});
  await abrir();assert.match(texto(nos['tar-detalhe']),/Sem vencimento → 25\/12\/2026/);
  for(const situacao of ['dispensada','a_fazer','concluida','conferida']){
    tarefa={...tarefa,situacao,pode_reativar:false,pode_alterar_vencimento:false,pode_executar:true,pode_gerir:true};
    await abrir();assert(!botao(nos['tar-detalhe'],'Reativar tarefa'));assert(!botao(nos['tar-detalhe'],'Alterar vencimento'));
  }
  tarefa={...tarefa,situacao:'dispensada',pode_reativar:undefined,pode_alterar_vencimento:undefined};
  await abrir();assert(!botao(nos['tar-detalhe'],'Reativar tarefa'),'DTO sem flag não concede a nova ação');
  tarefa={...tarefa,situacao:'a_fazer',pode_reativar:false,pode_alterar_vencimento:true};
  await abrir();await botao(nos['tar-detalhe'],'Alterar vencimento').emitir('click');d=dialogo();
  campo(d,'vencimento').value='2026-12-26';campo(d,'motivo').value='Sessão anterior';
  const antesSessao=mutacoes().length;ctx.Sessao.usuario={id:9};await d.emitir('submit');
  assert.strictEqual(mutacoes().length,antesSessao,'Formulário antigo não envia após trocar a sessão');
  assert.match(texto(d),/sessão/i);await botao(d,'Cancelar').emitir('click');
  assert.strictEqual(run('TarefasUI.camposRegra().find(c=>c.nome==="dia").rotulo'),'Dia do vencimento');
  assert.match(run('TarefasUI.camposRegra().find(c=>c.nome==="inicio_dia").ajuda'),/previsto/);
  assert.strictEqual(avisos.length,0);
  console.log('OK - ações UI: reativar, vencimento, permissões, cancelar, falhas, revisão, sessão e histórico seguro');
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
