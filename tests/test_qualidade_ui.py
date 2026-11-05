"""Qualidade: interface sintética, autorização, revisão e respostas em trânsito."""
from pathlib import Path
import shutil
import subprocess


def main():
    node = shutil.which("node")
    if not node:
        print("PULADO - qualidade UI: Node não instalado")
        return 0
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const todas=['aba.qualidade','qualidade.registrar','qualidade.gerir','qualidade.validar','qualidade.exportar','qualidade.custos','aba.tarefas'];
const elementos=e=>[e,...e.children.flatMap(elementos)];
const catalogo={clientes:[{id:1,nome:'Empresa sintética'}],setores:[{id:2,nome:'Fiscal'}],
 usuarios:[{id:3,nome:'Pessoa sintética',setor_ids:[2]},{id:9,nome:'Outro setor',setor_ids:[8]}],tipos:[{valor:'erro',rotulo:'Erro'}],
 criticidades:[{valor:'alta',rotulo:'Alta'}],modelos:[{setor:'Fiscal',atividades:['Conferir documentos']}],
 permissoes:{registrar:true,gerir:true,validar:true,exportar:true,custos:true},anexos:{disponivel:true,limite_bytes:10485760}};
const painel={formato:'qualidade_painel_v1',referencia:'2026-10-30',
 kpis:[{chave:'entregues_no_prazo',rotulo:'Entregas no prazo',valor:'75.00',unidade:'percentual',numerador:3,denominador:4,formula:'3 / 4 × 100'},
 {chave:'tempo_medio_resolucao_dias',rotulo:'Tempo médio de resolução',valor:'6.00',unidade:'dias',denominador:1,formula:'Tempo total / ocorrências solucionadas'},
 {chave:'amostra_sem_numerador',rotulo:'Amostra sem numerador',valor:null,unidade:'dias',numerador:null,denominador:0,formula:'Sem ocorrências solucionadas'},
 {chave:'numerador_zero',rotulo:'Proporção com zero observado',valor:'0.00',unidade:'percentual',numerador:0,denominador:4,formula:'0 / 4 × 100'}],
 totais:{tarefas:8,concluidas:4,pendentes:4,atrasadas:1,ocorrencias:1,ocorrencias_abertas:1,planos:1,planos_pendentes:1},
 semaforo:{verde:3,amarelo:3,vermelho:1,neutro:1},por_colaborador:[{usuario_id:3,nome:'Pessoa sintética',tarefas_concluidas:4,tarefas_pendentes:3,minutos:90,horas:'1.50',custo_total:'100.00'}],
 por_setor:[{setor_id:2,nome:'Fiscal',tarefas:8,concluidas:4,pendentes:4,atrasadas:1,ocorrencias:1,nao_conformidades_abertas:0}],
 alertas:[{tipo:'ocorrencias',rotulo:'Ocorrências em atenção',quantidade:1,cor:'vermelho',itens:[{entidade:'ocorrencia',id:4,titulo:'<img src=x>',cliente_id:1,setor_id:2,responsavel_usuario_id:3,prazo:'2026-10-29'}]}],
 custos:{permitido:true,minutos:90,horas:'1.50',custo_total:'100.00',custo_informado:'100.00',lancamentos_sem_custo:0,formula:'Minutos / 60 × custo/hora'},
 dimensoes:{operacao:{total:8,pendentes:4},risco:{ocorrencias_criticas:1,nao_conformidades_abertas:0},engajamento:{aguardando_cliente:2,sem_movimento:1},progresso:{concluidas:3,total:8,percentual:'37.50'}},
 metodologia:['O conjunto segue os filtros.']};
const ocorrencia={id:4,revision:7,data:'2026-10-30',cliente_id:1,cliente_nome:'Empresa sintética',setor_id:2,setor_nome:'Fiscal',
 responsavel_usuario_id:3,responsavel_nome:'Pessoa sintética',tipo:'erro',descricao:'<script>Descrição sintética</script>',criticidade:'alta',prazo:'2026-11-03',situacao:'aberta',
 pode_editar:true,pode_comentar:true,pode_transicionar:true,pode_validar:true,transicoes_permitidas:['em_tratamento'],
 historico:[{tipo:'criacao',usuario_login:'qa',criado_em:'2026-10-30T12:00:00+00:00',comentario:'Criada'},
 {tipo:'transicao',usuario_login:'qa',criado_em:'2026-10-30T13:00:00+00:00',antes:{situacao:'aberta'},depois:{situacao:'em_tratamento'}}],
 planos:[],anexos:[{id:5,nome:'evidência sintética.pdf',tamanho:250}]};
const plano={...ocorrencia,id:6,revision:2,ocorrencia_id:4,causa:'Causa sintética',descricao:'Rever processo',tipo:'corretiva',situacao:'aguardando_validacao',transicoes_permitidas:['validado','em_andamento'],pode_editar:false};
const horas={id:7,revision:3,data:'2026-10-30',cliente_id:1,setor_id:2,usuario_id:3,minutos:90,custo_hora:'66.67',custo_total:'100.01',descricao:'Conferência sintética',pode_cancelar:true};
function ambiente(permissoes=todas,registros={}){
 const ocorrenciaLocal=registros.ocorrencia||ocorrencia,planoLocal=registros.plano||plano;
 const doc={listeners:{},createElement(tag){const classes=new Set();return {tagName:tag,children:[],attributes:{},listeners:{},value:'',files:[],checked:false,disabled:false,hidden:false,_text:'',parent:null,
  set textContent(v){this._text=String(v??'');this.children=[];},get textContent(){return this._text+this.children.map(e=>e.textContent).join('');},
  set innerHTML(v){throw Error('HTML dinâmico não permitido');},
  append(...e){for(const x of e){this.children.push(x);x.parent=this;}},appendChild(e){this.append(e);return e;},
  setAttribute(k,v){this.attributes[k]=String(v);},removeAttribute(k){delete this.attributes[k];},
  addEventListener(t,fn){(this.listeners[t]||=[]).push(fn);},removeEventListener(){},
  async emit(t){for(const fn of this.listeners[t]||[])await fn({target:this,key:'',preventDefault(){}});},
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);this.parent=null;},
  focus(){doc.activeElement=this;},click(){if(this.tagName==='a')downloads.push(this.download);},get isConnected(){return true;},
  classList:{add(...v){v.forEach(x=>classes.add(x));},remove(...v){v.forEach(x=>classes.delete(x));},toggle(v,on){on?classes.add(v):classes.delete(v);},contains(v){return classes.has(v);}},
  querySelectorAll(){return elementos(this).filter(e=>['button','input','select','textarea'].includes(e.tagName));},querySelector(){return this.querySelectorAll()[0]||null;},getClientRects(){return [{}];},
 };},addEventListener(t,fn){(this.listeners[t]||=[]).push(fn);},removeEventListener(){},dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);}};
 doc.body=doc.createElement('body');const alvo=doc.createElement('section');doc.body.append(alvo);
 const permis=new Set(permissoes),requests=[],pending=[],downloads=[];
 let defer=false,postError=null,blobDefer=false,catalogoError=null;
 const blobs=[],catalogoLocal=JSON.parse(JSON.stringify(catalogo));
 const ctx={document:doc,console,URLSearchParams,Intl,Date,FormData:class{constructor(){this.itens=[];}append(k,v){this.itens.push([k,v]);}},
  URL:{createObjectURL(){return 'blob:sintetico';},revokeObjectURL(){}},
  Sessao:{usuario:{id:3},pode:p=>permis.has(p)},Abas:{registrar(){}},TarefasUI:{abrirContexto(v){ctx.tarefaAberta=v;}},
  api:async(url,opcoes={})=>{requests.push({url,opcoes});if(defer)return new Promise((resolve,reject)=>pending.push({resolve,reject,url,opcoes}));
   if(opcoes.method&&opcoes.method!=='GET'){if(postError)throw postError;return {...ocorrencia,revision:8};}
   if(url.includes('/relatorio.')||url.includes('/download'))return {headers:{get(){return url.includes('/download')?"attachment; filename*=UTF-8''evid%C3%AAncia.pdf":'attachment; filename="sintetico.pdf"';}},blob:async()=>blobDefer?new Promise(resolve=>blobs.push(resolve)):{}};
   if(url.includes('/catalogo')){if(catalogoError)throw catalogoError;return catalogoLocal;}if(url.includes('/painel'))return painel;
   if(/\/ocorrencias\/4(?:\?|$)/.test(url))return ocorrenciaLocal;
   if(url.includes('/ocorrencias'))return {itens:[ocorrenciaLocal],total:1};
   if(/\/planos\/6(?:\?|$)/.test(url))return planoLocal;
   if(url.includes('/planos'))return {itens:[planoLocal],total:1};
   if(url.includes('/horas'))return {itens:[horas],total:1};
   return {itens:[],total:0};},
  apiDownload:async(url)=>{const r=await ctx.api(url);await r.blob();downloads.push('sintetico.pdf');return 'sintetico.pdf';},toast(){},
 };
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/qualidade.js','utf8'),ctx);
 ctx.alvo=alvo;const get=id=>elementos(doc.body).find(e=>e.id===id);
 return {ctx,doc,alvo,get,requests,pending,downloads,permis,blobs,catalogo:catalogoLocal,
  async montar(){await vm.runInContext('QualidadeUI.montar(alvo)',ctx);},
  adiar(v){defer=v;},adiarBlob(v){blobDefer=v;},falharCatalogo(v){catalogoError=v;},falhar(v){postError=v;},run(s){return vm.runInContext(s,ctx);}};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const bloqueado=ambiente([]);await bloqueado.montar();assert.strictEqual(bloqueado.requests.length,0);
 let a=ambiente();await a.montar();
 assert(a.get('qua-painel'));assert(a.alvo.textContent.includes('75,00%'));
 assert(a.alvo.textContent.includes('<img src=x>'));assert(!elementos(a.alvo).some(e=>e.tagName==='img'));
 assert(a.alvo.textContent.includes('R$ 100,00'));assert(a.alvo.textContent.includes('3 / 4 × 100'));
 assert(a.get('qua-kpi-tempo_medio_resolucao_dias').textContent.includes('6,00 dias'));
 assert(a.get('qua-kpi-tempo_medio_resolucao_dias').textContent.includes('1 registro na amostra'));
 assert(!a.get('qua-kpi-tempo_medio_resolucao_dias').textContent.includes('0 de 1 registros'),'Média sem numerador não inventa zero');
 assert(a.get('qua-kpi-amostra_sem_numerador').textContent.includes('0 registros na amostra'));
 assert(!a.get('qua-kpi-amostra_sem_numerador').textContent.includes('0 de 0 registros'),'Numerador nulo também permanece ausente');
 assert(a.get('qua-kpi-entregues_no_prazo').textContent.includes('3 de 4 registros'));
 assert(a.get('qua-kpi-numerador_zero').textContent.includes('0 de 4 registros'),'Zero informado deve ser preservado');
 assert.strictEqual(a.run('QualidadeUI.moeda(null)'),'Sem dados');
 assert.strictEqual(a.run('QualidadeUI.moeda("1234.50")'),'R$ 1.234,50');
 assert.strictEqual(a.run('JSON.stringify(QualidadeUI.intervalo("semanal","2026-11-01"))'),'{"de":"2026-10-26","ate":"2026-11-01"}');
 assert.strictEqual(a.run('JSON.stringify(QualidadeUI.intervalo("mensal","2024-02-12"))'),'{"de":"2024-02-01","ate":"2024-02-29"}');
 await a.get('qua-tab-ocorrencias').emit('click');assert(a.get('qua-abrir-ocorrencia-4'));
 await a.get('qua-abrir-ocorrencia-4').emit('click');assert(a.get('qua-detalhe'));
 assert(a.alvo.textContent.includes('Aberta → Em tratamento'),'Histórico explica o movimento sem comentário');
 assert(a.alvo.textContent.includes('<script>Descrição sintética</script>'));assert(!elementos(a.alvo).some(e=>e.tagName==='script'));
 await a.get('qua-editar').emit('click');assert(a.get('qua-form'));
 let n=a.requests.length;assert(!a.requests.slice(n).some(x=>x.opcoes.method==='PATCH'));
 a.get('qua-campo-descricao').value='Alteração sintética';a.falhar(Object.assign(new Error('Revisão desatualizada'),{status:409}));
 await a.get('qua-form').emit('submit');let req=a.requests.at(-1);
 assert.strictEqual(req.opcoes.method,'PATCH');assert.strictEqual(req.opcoes.json.revision,7);
 assert.strictEqual(req.opcoes.json.descricao,'Alteração sintética');assert(a.get('qua-form'),'409 preserva formulário');
 assert(a.get('qua-form-erro').textContent.includes('Revisão desatualizada'));
 a.ctx.Sessao.usuario={id:8};n=a.requests.length;await a.get('qua-form').emit('submit');assert.strictEqual(a.requests.length,n,'Identidade alterada bloqueia envio');

 a=ambiente();await a.montar();await a.get('qua-tab-ocorrencias').emit('click');await a.get('qua-nova-ocorrencia').emit('click');
 for(const [k,v] of Object.entries({cliente_id:'1',setor_id:'2',responsavel_usuario_id:'3',tipo:'erro',criticidade:'alta',descricao:'Registro de teste',data:'2026-10-30',prazo:'2026-11-04'}))a.get('qua-campo-'+k).value=v;
 n=a.requests.length;await a.get('qua-form').emit('submit');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');
 assert(req);assert.strictEqual(req.url,'/api/qualidade/ocorrencias');assert.strictEqual(req.opcoes.json.cliente_id,1);
 assert(!('usuario_id' in req.opcoes.json),'Não envia autoria escolhida pelo navegador');
 assert(!a.get('qua-form'),'Formulário fecha após sucesso');

 a=ambiente();await a.montar();a.adiar(true);
 const antigo=a.get('qua-atualizar').emit('click');const p1=a.pending.shift();assert(p1);
 const novo=a.get('qua-aplicar').emit('click');const p2=a.pending.shift();assert(p2);
 p2.resolve({...painel,kpis:[{chave:'x',rotulo:'Valor atual',valor:22,unidade:'numero',formula:'Atual'}]});await novo;
 p1.resolve({...painel,kpis:[{chave:'x',rotulo:'Retorno antigo privado',valor:999,unidade:'numero',formula:'Antigo'}]});await antigo;
 assert(a.alvo.textContent.includes('Valor atual'));assert(!a.alvo.textContent.includes('Retorno antigo privado'));
 a.adiar(false);await a.get('qua-tab-relatorios').emit('click');await a.get('qua-exportar-xlsx').emit('click');
 assert(a.requests.some(r=>r.url.startsWith('/api/qualidade/relatorio.xlsx?')));assert.strictEqual(a.downloads.length,1);
 a.permis.delete('qualidade.exportar');n=a.downloads.length;await a.get('qua-exportar-xlsx').emit('click');assert.strictEqual(a.downloads.length,n);
 a.doc.dispatchEvent({type:'sessao:encerrada'});assert(!a.get('qua-painel'));assert(!a.alvo.textContent.includes('Pessoa sintética'));

 a=ambiente();await a.montar();await a.get('qua-tab-relatorios').emit('click');a.adiarBlob(true);
 const download=a.get('qua-exportar-pdf').emit('click');await settle();assert.strictEqual(a.blobs.length,1);
 a.ctx.Sessao.usuario={id:18};a.blobs.shift()({});await download;
 assert.strictEqual(a.downloads.length,0,'Download privado não deve chegar à nova sessão');

 a=ambiente();a.falharCatalogo(new Error('Catálogo temporariamente indisponível'));await a.montar();assert(a.get('qua-status').textContent.includes('indisponível'));
 a.falharCatalogo(null);await a.get('qua-atualizar').emit('click');assert(a.get('qua-painel'),'Atualizar tenta recuperar catálogo inicial');

 a=ambiente(todas.filter(p=>!['qualidade.custos','qualidade.exportar'].includes(p)));await a.montar();
 assert(!a.alvo.textContent.includes('R$ 100'),'Valores de custo não são desenhados sem permissão');
 await a.get('qua-tab-horas').emit('click');await a.get('qua-novas-horas').emit('click');assert(!a.get('qua-campo-custo_hora'));
 await a.get('qua-form-cancelar').emit('click');await a.get('qua-tab-relatorios').emit('click');assert(a.get('qua-exportar-pdf').disabled);

 a=ambiente();await a.montar();await a.get('qua-tab-planos').emit('click');await a.get('qua-novo-plano').emit('click');
 a.get('qua-campo-ocorrencia_id').value='4';await a.get('qua-campo-ocorrencia_id').emit('change');
 assert(!a.get('qua-campo-responsavel_usuario_id').children.some(o=>o.value==='9'),'Responsável do plano pertence ao setor da ocorrência');
 for(const [k,v] of Object.entries({responsavel_usuario_id:'3',tipo:'preventiva',causa:'Causa',descricao:'Prevenir repetição',prazo:'2026-11-04'}))a.get('qua-campo-'+k).value=v;
 n=a.requests.length;await a.get('qua-form').emit('submit');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');
 assert.strictEqual(req.url,'/api/qualidade/planos');assert.strictEqual(req.opcoes.json.ocorrencia_id,4);assert(!('cliente_id' in req.opcoes.json));
 await a.get('qua-abrir-plano-6').emit('click');assert(!a.get('qua-editar'));
 await a.get('qua-transicao').emit('click');a.get('qua-campo-situacao').value='validado';a.get('qua-campo-comentario').value='Resultado conferido';
 n=a.requests.length;await a.get('qua-form').emit('submit');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');
 assert.strictEqual(req.url,'/api/qualidade/planos/6/transicao');assert.strictEqual(req.opcoes.json.revision,2);

 await a.get('qua-tab-horas').emit('click');await a.get('qua-novas-horas').emit('click');
 for(const [k,v] of Object.entries({cliente_id:'1',setor_id:'2',minutos:'90',custo_hora:'60.50',descricao:'Esforço sintético'}))a.get('qua-campo-'+k).value=v;
 n=a.requests.length;await a.get('qua-form').emit('submit');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');
 assert.strictEqual(req.url,'/api/qualidade/horas');assert.strictEqual(req.opcoes.json.custo_hora,'60.50');assert.strictEqual(req.opcoes.json.minutos,90);assert(!('usuario_id' in req.opcoes.json));
 await a.get('qua-cancelar-horas-7').emit('click');n=a.requests.length;await a.get('qua-form').emit('submit');assert.strictEqual(a.requests.length,n,'Cancelamento exige motivo');
 a.get('qua-campo-motivo').value='Lançamento duplicado';await a.get('qua-form').emit('submit');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');assert.strictEqual(req.opcoes.json.revision,3);

 await a.get('qua-tab-ocorrencias').emit('click');await a.get('qua-abrir-ocorrencia-4').emit('click');
 a.get('qua-anexo-arquivo').files=[{name:'arquivo.exe',size:12}];n=a.requests.length;await a.get('qua-anexo-enviar').emit('click');assert.strictEqual(a.requests.length,n);
 a.get('qua-anexo-arquivo').files=[{name:'evidencia.pdf',size:250}];await a.get('qua-anexo-enviar').emit('click');req=a.requests.slice(n).find(x=>x.opcoes.method==='POST');
 assert.strictEqual(req.url,'/api/qualidade/ocorrencias/4/anexos');assert.strictEqual(req.opcoes.body.itens[0][0],'arquivo');
 await a.get('qua-anexo-5').emit('click');assert.strictEqual(a.downloads.at(-1),'evidência.pdf','Preserva nome UTF-8 e extensão da evidência');
 a.adiar(true);const tardio=a.get('qua-abrir-ocorrencia-4').emit('click');const detalheTardio=a.pending.shift();
 await a.get('qua-tab-modelos').emit('click');detalheTardio.resolve(ocorrencia);await tardio;assert(a.get('qua-detalhe').hidden,'Detalhe tardio não invade outra visão');

 a=ambiente(['aba.qualidade','qualidade.gerir']);await a.montar();await a.get('qua-tab-ocorrencias').emit('click');
 assert(!a.get('qua-nova-ocorrencia'),'Gestão sem registrar não cria ocorrências');await a.get('qua-abrir-ocorrencia-4').emit('click');
 await a.get('qua-editar').emit('click');assert(a.get('qua-form'),'Gestor com DTO autorizado pode editar sem registrar');
 a.get('qua-campo-descricao').value='Ajuste do gestor';n=a.requests.length;await a.get('qua-form').emit('submit');
 assert(a.requests.slice(n).some(r=>r.opcoes.method==='PATCH'));
 await a.get('qua-abrir-ocorrencia-4').emit('click');await a.get('qua-comentar').emit('click');a.get('qua-campo-comentario').value='Acompanhamento do gestor';
 a.permis.delete('qualidade.gerir');n=a.requests.length;await a.get('qua-form').emit('submit');assert.strictEqual(a.requests.length,n,'Gestão revogada impede envio do formulário já aberto');

 // Lista e detalhe devem preservar a classificação do servidor, inclusive no
 // fechamento tardio e nas não conformidades ainda dentro do prazo.
 const casosCor=[
  ['ocorrencia','Ocorrência resolvida com atraso',{situacao:'resolvida',prazo:'2026-11-02',resolvida_em:'2026-11-04T12:00:00+00:00',cor:'vermelho'},'vermelho'],
  ['ocorrencia','Não conformidade aberta',{situacao:'aberta',tipo:'nao_conformidade',criticidade:'baixa',prazo:'2099-11-10',cor:'vermelho'},'vermelho'],
  ['plano','Plano validado com atraso',{situacao:'validado',prazo:'2026-11-02',validado_em:'2026-11-04T12:00:00+00:00',cor:'vermelho'},'vermelho'],
  ['ocorrencia','Solução dentro do prazo',{situacao:'resolvida',prazo:'2026-11-10',resolvida_em:'2026-11-04T12:00:00+00:00',cor:'verde'},'verde'],
  ['plano','Plano em andamento',{situacao:'em_andamento',prazo:'2099-11-10',cor:'amarelo'},'amarelo'],
  ['ocorrencia','Sem comprovação de pontualidade',{situacao:'resolvida',resolvida_em:'',cor:'neutro'},'neutro'],
  ['plano','DTO sem classificação',{situacao:'validado'},'neutro'],
  ['ocorrencia','Classificação não reconhecida',{situacao:'resolvida',cor:'verde classe-indevida'},'neutro'],
 ];
 for(const [entidade,descricao,campos,esperada] of casosCor){
  const registro={...(entidade==='ocorrencia'?ocorrencia:plano),descricao,...campos};
  a=ambiente(todas,{[entidade]:registro});await a.montar();
  await a.get(entidade==='ocorrencia'?'qua-tab-ocorrencias':'qua-tab-planos').emit('click');
  const badges=e=>elementos(e).filter(n=>(n.className||'').split(' ').includes('qua-badge'));
  let encontrados=badges(a.get('qua-conteudo'));
  assert.strictEqual(encontrados.length,1,descricao+': um indicador na linha');
  assert.strictEqual(encontrados[0].className,'qua-badge qua-'+esperada,descricao+': cor da lista');
  await a.get(`qua-abrir-${entidade}-${registro.id}`).emit('click');
  encontrados=badges(a.get('qua-detalhe'));
  assert.strictEqual(encontrados.length,1,descricao+': um indicador no detalhe');
  assert.strictEqual(encontrados[0].className,'qua-badge qua-'+esperada,descricao+': cor do detalhe');
 }
 console.log('OK - qualidade UI: painel, escopo, formulários, revisão, downloads e respostas atrasadas');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    resultado = subprocess.run([node, "-e", script], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, encoding="utf-8", timeout=90)
    print(resultado.stdout, end="")
    print(resultado.stderr, end="")
    return resultado.returncode or int("OK - qualidade UI:" not in resultado.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
