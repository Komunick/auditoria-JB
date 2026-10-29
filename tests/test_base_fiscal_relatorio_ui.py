"""Download Fiscal: fonte integral, permissões e descarte de respostas antigas."""
from pathlib import Path
import shutil
import subprocess


def main():
    raiz = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    if not node:
        print('PULADO - relatório Fiscal UI: Node não instalado')
        return 0
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const downloads = [], urls = [], revogadas = [];
const doc = {listeners: {},
  addEventListener(tipo, fn) { (this.listeners[tipo] ||= []).push(fn); },
  dispatchEvent(e) { for (const fn of this.listeners[e.type] || []) fn(e); },
  createElement(tag) {
    return {tagName:tag,children:[],attributes:{},listeners:{},value:'',files:[],
      disabled:false,hidden:false,className:'',_texto:'',
      set textContent(v) { this._texto=String(v ?? ''); this.children=[]; },
      get textContent() { return this._texto + this.children.map(e=>e.textContent).join(''); },
      set innerHTML(v) { throw Error('HTML dinâmico não permitido'); },
      append(...itens) { this.children.push(...itens); },
      appendChild(item) { this.append(item); return item; },
      setAttribute(nome,valor) { this.attributes[nome]=String(valor); },
      addEventListener(tipo,fn) { (this.listeners[tipo] ||= []).push(fn); },
      async emit(tipo) { for (const fn of this.listeners[tipo] || []) await fn({preventDefault(){},target:this}); },
      click() { if (this.tagName==='a') downloads.push({href:this.href,nome:this.download}); },
      focus() { doc.activeElement=this; },
      classList:{add(){},remove(){},toggle(){}},
    };
  }};
const elementos = e => [e,...e.children.flatMap(elementos)];
const alvo=doc.createElement('section');
const get=id=>elementos(alvo).find(e=>e.id===id);
let permissoes=new Set(['aba.clientes','clientes.importar']), pedidos=[], previas=[], chamadas=[];
const ctx={document:doc,console,Abas:{registrar(){}},
  Sessao:{usuario:{id:1},pode(p){return permissoes.has(p);}},
  FormData:class {constructor(){this.itens=[];} append(k,v){this.itens.push([k,v]);}},
  URL:{createObjectURL(blob){const url=`blob:teste-${urls.length}`;urls.push({url,blob});return url;},revokeObjectURL(url){revogadas.push(url);}},
  apiUpload(url,arquivo){return new Promise((resolve,reject)=>previas.push({resolve,reject,url,arquivo}));},
  api(url,opcoes){chamadas.push({url,opcoes});return new Promise((resolve,reject)=>pedidos.push({resolve,reject}));},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('webui/clientes.js','utf8'),ctx);
ctx.alvo=alvo;vm.runInContext('BaseFiscalUI.montar(alvo)',ctx);
const dados={somente_leitura:true,nome_arquivo:'base-sintetica.xlsx',hash_arquivo:'a'.repeat(64),
  formato:'base_fiscal_v1',avisos:[],abas:[{nome:'Carteira',tipo:'principal',linha_cabecalho:2,total:60}],
  contagens:{linhas:60,cnpjs_distintos:60,documentos_validos:60,documentos_pendentes:0,grupos_duplicados:0,sem_movimento:0,com_pendencias:0},
  linhas:Array.from({length:60},(_,i)=>({id:`1:${i+3}`,aba:'Carteira',linha:i+3,nome:`Empresa sintética ${i}`,
    documento:'01987654000100',documento_status:'valido',regime:'Simples Nacional',responsavel_fiscal_informado:'Pessoa sintética',
    contato_nome:'Contato sintético',pendencias:[],origem:{},duplicado_em:[]}))};
const turno=()=>new Promise(resolve=>setImmediate(resolve));
async function conferir(nome='base.xlsx') {
  const arquivo={name:nome,size:1024};
  get('bf-arquivo').files=[arquivo];await get('bf-arquivo').emit('change');
  const fim=get('bf-ler').emit('click');
  previas.shift().resolve(dados);await fim;
  return arquivo;
}
function respostaControlada() {
  let entregar,recusar;
  const blob=new Promise((resolve,reject)=>{entregar=resolve;recusar=reject;});
  return {resposta:{blob:()=>blob},entregar,recusar};
}
async function iniciar() {
  const fim=get('bf-relatorio').emit('click');
  const pedido=pedidos.shift();assert(pedido);
  return {fim,pedido};
}
async function concluir(pedido,fim,blob={type:'application/xlsx'}) {
  const controle=respostaControlada();pedido.resolve(controle.resposta);await turno();
  controle.entregar(blob);await fim;
}
(async()=>{
  assert(!get('bf-relatorio') || get('bf-relatorio').disabled);
  await conferir();
  assert(get('bf-relatorio'),'A prévia deve oferecer relatório completo');
  assert.strictEqual(get('bf-relatorio').disabled,true);
  await get('bf-relatorio').emit('click');assert.strictEqual(chamadas.length,0);
  permissoes.add('clientes.exportar');
  const arquivo=await conferir();
  assert.strictEqual(get('bf-relatorio').disabled,false);
  assert(get('bf-relatorio').textContent.includes('Baixar relatório completo (.xlsx)'));
  assert(alvo.textContent.includes('Correções') && alvo.textContent.includes('importação'));
  get('bf-busca').value='não existe';await get('bf-busca').emit('input');
  get('bf-situacao').value='pendencias';await get('bf-situacao').emit('change');
  const primeiro=await iniciar();
  assert.strictEqual(get('bf-relatorio').disabled,true);
  await get('bf-relatorio').emit('click');assert.strictEqual(chamadas.length,1,'Não duplicar pedidos em andamento');
  assert.strictEqual(chamadas[0].url,'/api/clientes/base-fiscal/relatorio');
  assert.strictEqual(chamadas[0].opcoes.method,'POST');
  assert.deepStrictEqual(chamadas[0].opcoes.body.itens.map(p=>p[0]),['arquivo','hash_esperado']);
  assert.strictEqual(chamadas[0].opcoes.body.itens[0][1],arquivo);
  assert.strictEqual(chamadas[0].opcoes.body.itens[1][1],dados.hash_arquivo);
  await concluir(primeiro.pedido,primeiro.fim);
  assert.strictEqual(downloads.length,1);
  assert.strictEqual(downloads[0].nome,'conferencia-base-fiscal.xlsx');
  assert.deepStrictEqual(revogadas,[urls[0].url]);
  assert.strictEqual(get('bf-relatorio').disabled,false);
  assert(!get('bf-status').textContent.includes('Gerando'));

  // Erro explícito mantém prévia e permite repetir; texto é exibido literalmente.
  let atual=await iniciar();atual.pedido.reject(new Error('<b>Falha temporária</b>'));await atual.fim;
  assert(get('bf-status').textContent.includes('<b>Falha temporária</b>'));
  assert.strictEqual(get('bf-relatorio').disabled,false);
  atual=await iniciar();await concluir(atual.pedido,atual.fim);assert.strictEqual(downloads.length,2);

  // Arquivo substituído com a resposta HTTP pendente.
  atual=await iniciar();
  get('bf-arquivo').files=[{name:'outra.xlsx',size:1024}];await get('bf-arquivo').emit('change');
  let leuBlob=false;atual.pedido.resolve({blob(){leuBlob=true;return Promise.resolve({});}});await atual.fim;
  assert(!leuBlob);assert.strictEqual(downloads.length,2);assert.strictEqual(get('bf-resultado').textContent,'');

  // Limpeza durante a leitura do blob impede o clique e a criação de URL.
  await conferir();atual=await iniciar();let controle=respostaControlada();
  atual.pedido.resolve(controle.resposta);await turno();
  await get('bf-limpar').emit('click');controle.entregar({});await atual.fim;
  assert.strictEqual(downloads.length,2);assert.strictEqual(urls.length,2);

  // Nova leitura não recebe o estado, erro ou botão da requisição antiga.
  await conferir();atual=await iniciar();await conferir('nova-leitura.xlsx');
  atual.pedido.reject(new Error('erro privado atrasado'));await atual.fim;
  assert(!alvo.textContent.includes('erro privado atrasado'));
  assert.strictEqual(get('bf-relatorio').disabled,false);
  let novo=await iniciar();await concluir(novo.pedido,novo.fim);assert.strictEqual(downloads.length,3);

  // Troca de identidade e perda de cada permissão invalidam respostas em voo.
  for(const perda of ['identidade','aba.clientes','clientes.importar','clientes.exportar']) {
    permissoes=new Set(['aba.clientes','clientes.importar','clientes.exportar']);
    await conferir();atual=await iniciar();controle=respostaControlada();
    atual.pedido.resolve(controle.resposta);await turno();
    if(perda==='identidade') ctx.Sessao.usuario={id:2};else permissoes.delete(perda);
    controle.entregar({});await atual.fim;
    assert.strictEqual(downloads.length,3,perda);assert.strictEqual(get('bf-resultado').textContent,'',perda);
  }
  permissoes=new Set(['aba.clientes','clientes.importar','clientes.exportar']);
  await conferir();atual=await iniciar();doc.dispatchEvent({type:'sessao:encerrada'});
  atual.pedido.reject(new Error('erro privado da sessão encerrada'));await atual.fim;
  assert(!alvo.textContent.includes('erro privado da sessão encerrada'));assert.strictEqual(downloads.length,3);

  // Sessão muda antes do clique, sem depender de um evento de encerramento.
  await conferir();ctx.Sessao.usuario={id:3};const antes=chamadas.length;
  await get('bf-relatorio').emit('click');assert.strictEqual(chamadas.length,antes);
  assert.strictEqual(get('bf-resultado').textContent,'');

  // Hash divergente exige nova prévia; não há retry sobre a fonte antiga.
  await conferir();atual=await iniciar();
  const divergente=new Error('Arquivo divergente');divergente.codigo='BASE_FISCAL_DIVERGENTE';
  atual.pedido.reject(divergente);await atual.fim;
  assert.strictEqual(get('bf-resultado').textContent,'');
  assert(/novamente|nova prévia/.test(get('bf-status').textContent));
  assert.strictEqual(downloads.length,3);assert.strictEqual(revogadas.length,urls.length);
  console.log('OK - relatório Fiscal UI: fonte/hash, autorização, repetição, erros e sessão/arquivo obsoletos');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    resultado = subprocess.run([node, '-e', script], cwd=raiz, check=False)
    return resultado.returncode


if __name__ == '__main__':
    raise SystemExit(main())
