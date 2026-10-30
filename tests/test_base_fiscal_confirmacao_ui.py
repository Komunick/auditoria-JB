"""Carga Fiscal: confirmação explícita, revalidação, repetição e sessão."""
from pathlib import Path
import shutil
import subprocess


def main():
    raiz = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        print("PULADO - confirmação Fiscal UI: Node não instalado")
        return 0
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const doc={listeners:{},
  addEventListener(t,fn){(this.listeners[t] ||= []).push(fn);},
  dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);},
  createElement(tag){return {tagName:tag,children:[],attributes:{},listeners:{},files:[],value:'',checked:false,disabled:false,hidden:false,_texto:'',
    set textContent(v){this._texto=String(v??'');this.children=[];},
    get textContent(){return this._texto+this.children.map(e=>e.textContent).join('');},
    set innerHTML(v){throw Error('Não usar HTML dinâmico na carga Fiscal');},
    append(...v){this.children.push(...v);},appendChild(v){this.append(v);return v;},
    setAttribute(k,v){this.attributes[k]=String(v);},
    addEventListener(t,fn){(this.listeners[t] ||= []).push(fn);},
    async emit(t){for(const fn of this.listeners[t]||[])await fn({target:this,preventDefault(){}});},
    focus(){doc.activeElement=this;},classList:{add(){},remove(){},toggle(){}},
  };}};
const elementos=e=>[e,...e.children.flatMap(elementos)],alvo=doc.createElement('section');
const get=id=>elementos(alvo).find(e=>e.id===id);
const basicas=['aba.clientes','clientes.importar'],permissaoCarga='clientes.importar_base_fiscal';
let permissoes=new Set(basicas),pedidos=[],leituras=[],chamadas=[];
const ctx={document:doc,console,Abas:{registrar(){}},
  Sessao:{usuario:{id:1},pode:p=>permissoes.has(p)},
  FormData:class{constructor(){this.itens=[];}append(k,v){this.itens.push([k,v]);}},
  apiUpload(url,arquivo){return new Promise((resolve,reject)=>leituras.push({resolve,reject}));},
  api(url,opcoes){chamadas.push({url,opcoes});return new Promise((resolve,reject)=>pedidos.push({resolve,reject}));},
};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/clientes.js','utf8'),ctx);
ctx.alvo=alvo;vm.runInContext('BaseFiscalUI.montar(alvo)',ctx);
const fonte={somente_leitura:true,formato:'base_fiscal_v1',hash_arquivo:'a'.repeat(64),nome_arquivo:'fonte-sintetica.xlsx',avisos:[],abas:[],contagens:{linhas:0},linhas:[]};
const linha=(i,status)=>({id:`1:${i+2}`,aba:'Fiscal sintético',linha:i+2,status,
  original:{nome:`Empresa sintética ${i}`,documento:'01987654000113'},proposto:{},
  efetivo:{nome:`Empresa sintética ${i}`,documento:'01987654000113',contato_nome:'Contato sintético'},
  alteracoes:[],decisao:'',observacao:'',pendencias:[],avisos:[],cadastro:null});
const previa={somente_leitura:true,formato:'base_fiscal_importacao_v1',hash_arquivo:fonte.hash_arquivo,hash_correcoes:'b'.repeat(64),
  cadastro_consultado_em:'2026-10-30T12:00:00+00:00',cadastro_disponivel:true,avisos:[],
  contagens:{linhas:3,incluir:1,existente:1,ignorar:1,pendente:0,conflito:0,alteradas:0},
  linhas:[linha(0,'incluir'),linha(1,'existente'),linha(2,'ignorar')]};
const fresca={...previa,contagens:{...previa.contagens,linhas:4,incluir:2},
  linhas:[...previa.linhas,{...linha(3,'incluir'),efetivo:{nome:'<b>Empresa nova conferida</b>',documento:'01987654000113'}}]};
const preparacao={formato:'base_fiscal_confirmacao_v1',token:'token-sintetico',expira_em_minutos:30,previa:fresca};
const recibo={formato:'base_fiscal_resultado_v1',importacao_id:17,repetida:false,
  contagens:{incluidas:2,existentes:1,ignoradas:1},hash_arquivo:fonte.hash_arquivo,hash_correcoes:previa.hash_correcoes,criado_em:'2026-10-30T12:10:00+00:00'};
async function base(){
  const arquivo={name:'fonte-sintetica.xlsx',size:100};get('bf-arquivo').files=[arquivo];await get('bf-arquivo').emit('change');
  const fim=get('bf-ler').emit('click');leituras.shift().resolve(fonte);await fim;
  const correcoes={name:'correcoes-sinteticas.xlsx',size:100};get('bf-correcoes').files=[correcoes];await get('bf-correcoes').emit('change');
  return {arquivo,correcoes};
}
async function revisar(dados=previa){
  const fim=get('bf-importacao-gerar').emit('click');pedidos.shift().resolve(dados);await fim;
}
async function preparar(){
  assert(get('bf-importacao-preparar'),'Prévia apta deve oferecer preparação para quem tem a permissão específica');
  const fim=get('bf-importacao-preparar').emit('click'),pedido=pedidos.shift();assert(pedido);return {fim,pedido};
}
async function pronta(){
  const arquivos=await base();await revisar();const atual=await preparar();atual.pedido.resolve(preparacao);await atual.fim;return arquivos;
}
async function aceitar(){get('bf-importacao-aceite').checked=true;await get('bf-importacao-aceite').emit('change');}
async function confirmar(){const fim=get('bf-importacao-confirmar').emit('click'),pedido=pedidos.shift();assert(pedido);return {fim,pedido};}
const erro=(codigo,mensagem='Revisão necessária')=>Object.assign(new Error(mensagem),{codigo,status:codigo===410?410:409});
(async()=>{
  await base();await revisar();assert(!get('bf-importacao-preparar'),'Permissão antiga não autoriza preparar a carga');
  permissoes.add(permissaoCarga);
  for(const bloqueio of ['pendente','conflito']){
    await revisar({...previa,contagens:{...previa.contagens,[bloqueio]:1},linhas:[...previa.linhas,linha(4,bloqueio)]});
    assert(!get('bf-importacao-preparar')||get('bf-importacao-preparar').disabled,'Pendências bloqueiam preparação');
  }
  await revisar({...previa,contagens:{...previa.contagens,incluir:0},linhas:[linha(1,'existente'),linha(2,'ignorar')]});
  assert(!get('bf-importacao-preparar')||get('bf-importacao-preparar').disabled,'Sem novas empresas não há carga');
  const arquivos=await base();await revisar();let atual=await preparar();
  let chamada=chamadas.at(-1);assert.strictEqual(chamada.url,'/api/clientes/base-fiscal/importacao/preparar');
  assert.deepStrictEqual(chamada.opcoes.body.itens.map(p=>p[0]),['arquivo','correcoes','hash_esperado','hash_correcoes_esperado']);
  assert.strictEqual(chamada.opcoes.body.itens[0][1],arquivos.arquivo);assert.strictEqual(chamada.opcoes.body.itens[1][1],arquivos.correcoes);
  assert.strictEqual(chamada.opcoes.body.itens[2][1],fonte.hash_arquivo);assert.strictEqual(chamada.opcoes.body.itens[3][1],previa.hash_correcoes);
  let antes=chamadas.length;await get('bf-importacao-preparar').emit('click');assert.strictEqual(chamadas.length,antes);
  atual.pedido.resolve(preparacao);await atual.fim;
  assert.strictEqual(get('bf-importacao-total-incluir').textContent,'2','Preparação deve mostrar o cadastro revalidado');
  assert(alvo.textContent.includes('<b>Empresa nova conferida</b>'));assert(!elementos(alvo).some(e=>e.tagName==='b'));
  assert(!get('bf-importacao-aceite').checked);assert(get('bf-importacao-confirmar').disabled);
  antes=chamadas.length;await get('bf-importacao-confirmar').emit('click');assert.strictEqual(chamadas.length,antes,'Não enviar sem aceite explícito');
  await aceitar();assert(!get('bf-importacao-confirmar').disabled);assert(get('bf-importacao-confirmar').textContent.includes('2'));
  atual=await confirmar();chamada=chamadas.at(-1);
  assert.strictEqual(chamada.url,'/api/clientes/base-fiscal/importacao/token-sintetico/confirmar');
  assert.deepStrictEqual(chamada.opcoes.body.itens.map(p=>p[0]),['arquivo','correcoes','confirmacao']);
  assert.strictEqual(chamada.opcoes.body.itens[0][1],arquivos.arquivo);assert.strictEqual(chamada.opcoes.body.itens[1][1],arquivos.correcoes);
  assert.strictEqual(chamada.opcoes.body.itens[2][1],'IMPORTAR EMPRESAS');
  antes=chamadas.length;await get('bf-importacao-confirmar').emit('click');assert.strictEqual(chamadas.length,antes,'Duplo clique não duplica requisição');
  atual.pedido.resolve(recibo);await atual.fim;
  assert(get('bf-importacao-recibo').textContent.includes('17'));
  for(const palavra of ['incluída','preservada','ignorada'])assert(get('bf-importacao-recibo').textContent.includes(palavra));
  assert(!get('bf-importacao-confirmar')||get('bf-importacao-confirmar').disabled);
  assert(!get('bf-importacao-aceite')||!get('bf-importacao-aceite').checked);

  // Uma resposta perdida pode ter confirmado a carga: repetir o mesmo token é seguro.
  await pronta();await aceitar();atual=await confirmar();atual.pedido.reject(new Error('Falha de rede'));await atual.fim;
  assert(/resultado|confirmar|verificar/i.test(get('bf-importacao-status').textContent));
  assert(!/nada foi gravado|nenhum cadastro.*gravado/i.test(get('bf-importacao-status').textContent));
  await aceitar();atual=await confirmar();assert(chamadas.at(-1).url.includes('token-sintetico/confirmar'));
  atual.pedido.resolve({...recibo,repetida:true});await atual.fim;
  assert(/anterior|já|repet/i.test(get('bf-importacao-recibo').textContent),'Resultado repetido deve ser explicado');

  for(const codigo of ['BASE_FISCAL_DESATUALIZADA','BASE_FISCAL_TOKEN_EXPIRADO']){
    await pronta();await aceitar();atual=await confirmar();atual.pedido.reject(erro(codigo));await atual.fim;
    assert(!get('bf-importacao-confirmar')||get('bf-importacao-confirmar').disabled,'Falha de revisão invalida confirmação');
    assert(!get('bf-importacao-aceite')||!get('bf-importacao-aceite').checked);
    assert(!get('bf-importacao-recibo'),'Conflito não pode mostrar sucesso');
  }
  // Não interpretar nem mostrar respostas de preparação de um arquivo anterior.
  await base();await revisar();atual=await preparar();get('bf-correcoes').files=[{name:'outra.xlsx',size:100}];await get('bf-correcoes').emit('change');
  atual.pedido.resolve(preparacao);await atual.fim;assert(!get('bf-importacao-aceite'));
  for(const perda of ['arquivo','identidade',permissaoCarga,'sessao']){
    permissoes=new Set([...basicas,permissaoCarga]);await pronta();await aceitar();
    const antigo=get('bf-importacao-confirmar');antes=chamadas.length;
    if(perda==='arquivo'){get('bf-correcoes').files=[{name:'nova.xlsx',size:100}];await get('bf-correcoes').emit('change');}
    else if(perda==='identidade')ctx.Sessao.usuario={id:2};else if(perda==='sessao')doc.dispatchEvent({type:'sessao:encerrada'});else permissoes.delete(perda);
    await antigo.emit('click');assert.strictEqual(chamadas.length,antes,perda+' deve impedir envio obsoleto');
  }
  for(const perda of ['arquivo','identidade',permissaoCarga,'sessao']){
    permissoes=new Set([...basicas,permissaoCarga]);await pronta();await aceitar();atual=await confirmar();
    if(perda==='arquivo'){get('bf-arquivo').files=[{name:'nova.xlsx',size:100}];await get('bf-arquivo').emit('change');}
    else if(perda==='identidade')ctx.Sessao.usuario={id:8};else if(perda==='sessao')doc.dispatchEvent({type:'sessao:encerrada'});else permissoes.delete(perda);
    atual.pedido.resolve({...recibo,importacao_id:99999});await atual.fim;
    assert(!alvo.textContent.includes('99999'),perda+' não deve exibir retorno privado antigo');
  }
  // Resposta estranha não habilita a gravação nem confirma um recibo errado.
  permissoes=new Set([...basicas,permissaoCarga]);await base();await revisar();atual=await preparar();
  atual.pedido.resolve({...preparacao,previa:{...fresca,hash_correcoes:'c'.repeat(64)}});await atual.fim;
  assert(!get('bf-importacao-aceite'));
  await base();await revisar();atual=await preparar();
  atual.pedido.resolve({...preparacao,previa:{...fresca,contagens:{...fresca.contagens,incluir:99}}});await atual.fim;
  assert(!get('bf-importacao-aceite'),'Não oferecer aceite de quantidades que divergem das linhas apresentadas');
  await pronta();await aceitar();atual=await confirmar();atual.pedido.resolve({...recibo,hash_arquivo:'d'.repeat(64)});await atual.fim;
  assert(!get('bf-importacao-recibo'),'Não exibir recibo de outros arquivos');
  console.log('OK - confirmação Fiscal UI: revisão fresca, aceite, idempotência, erros e isolamento de arquivo/sessão');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    return subprocess.run([node, "-e", script], cwd=raiz, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
