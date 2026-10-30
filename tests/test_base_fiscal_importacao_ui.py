"""Prévia da carga Fiscal: propostas, comparação e isolamento de arquivo/sessão."""
from pathlib import Path
import shutil
import subprocess


def main():
    raiz = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    if not node:
        print('PULADO - prévia de importação Fiscal UI: Node não instalado')
        return 0
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const doc={listeners:{},
  addEventListener(t,fn){(this.listeners[t] ||= []).push(fn);},
  dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);},
  createElement(tag){return {tagName:tag,children:[],attributes:{},listeners:{},files:[],value:'',disabled:false,hidden:false,_texto:'',
    set textContent(v){this._texto=String(v??'');this.children=[];},
    get textContent(){return this._texto+this.children.map(e=>e.textContent).join('');},
    set innerHTML(v){throw Error('Não usar HTML dinâmico');},
    append(...v){this.children.push(...v);},appendChild(v){this.append(v);return v;},
    setAttribute(k,v){this.attributes[k]=String(v);},
    addEventListener(t,fn){(this.listeners[t] ||= []).push(fn);},
    async emit(t){for(const fn of this.listeners[t]||[])await fn({target:this,preventDefault(){}});},
    focus(){doc.activeElement=this;},classList:{add(){},remove(){},toggle(){}},
  };}};
const elementos=e=>[e,...e.children.flatMap(elementos)],alvo=doc.createElement('section');
const get=id=>elementos(alvo).find(e=>e.id===id);
let permissoes=new Set(['aba.clientes','clientes.importar']),pedidos=[],previas=[],chamadas=[];
const ctx={document:doc,console,Abas:{registrar(){}},
  Sessao:{usuario:{id:1},pode:p=>permissoes.has(p)},
  FormData:class{constructor(){this.itens=[];}append(k,v){this.itens.push([k,v]);}},
  apiUpload(url,arquivo){return new Promise((resolve,reject)=>previas.push({resolve,reject}));},
  api(url,opcoes){chamadas.push({url,opcoes});return new Promise((resolve,reject)=>pedidos.push({resolve,reject}));},
};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('webui/clientes.js','utf8'),ctx);
ctx.alvo=alvo;vm.runInContext('BaseFiscalUI.montar(alvo)',ctx);
const fonte={somente_leitura:true,formato:'base_fiscal_v1',hash_arquivo:'a'.repeat(64),nome_arquivo:'fonte-sintetica.xlsx',avisos:[],abas:[],contagens:{linhas:0},linhas:[]};
const tipos=['incluir','existente','conflito','pendente','ignorar'];
const revisao={somente_leitura:true,formato:'base_fiscal_importacao_v1',hash_arquivo:fonte.hash_arquivo,hash_correcoes:'b'.repeat(64),
  cadastro_consultado_em:'2026-10-30T12:00:00+00:00',cadastro_disponivel:true,
  avisos:['Sem vínculo automático com usuário'],contagens:{linhas:60,incluir:12,existente:12,conflito:12,pendente:12,ignorar:12,alteradas:60},
  linhas:Array.from({length:60},(_,i)=>({id:`1:${i+2}`,aba:'Fiscal sintético',linha:i+2,status:tipos[i%5],
    original:{nome:`Original ${i}`,documento:'01987654000113',regime:'Simples Nacional',responsavel_fiscal:'Pessoa anterior',contato_nome:'Contato anterior'},
    proposto:{nome:`<b>Proposta ${i}</b>`,contato_nome:'Novo contato'},
    efetivo:{nome:`<b>Proposta ${i}</b>`,documento:'01987654000113',regime:'Simples Nacional',responsavel_fiscal:'Pessoa anterior',contato_nome:'Novo contato',sem_movimento:i===4?true:null},
    alteracoes:[{campo:'nome',antes:`Original ${i}`,depois:`<b>Proposta ${i}</b>`,celula:`H${i+2}`}],
    decisao:i%5===4?'ignorar':'manter',observacao:i%5===4?'Ocorrência repetida':'' ,pendencias:i%5===3?['Documento pendente']:[],avisos:['Responsável sem vínculo'],
    cadastro:i%5===1||i%5===2?{id:10+i,nome:`Cadastro ${i}`,documento:'01987654000113',contato_nome:'Contato cadastrado',situacao:'ativo',revision:3}:null}))};
const turno=()=>new Promise(r=>setImmediate(r));
async function conferir(){
  const arquivo={name:'fonte-sintetica.xlsx',size:100};get('bf-arquivo').files=[arquivo];await get('bf-arquivo').emit('change');
  const fim=get('bf-ler').emit('click');previas.shift().resolve(fonte);await fim;return arquivo;
}
async function selecionar(nome='correcoes.xlsx',size=100){const arquivo={name:nome,size};get('bf-correcoes').files=[arquivo];await get('bf-correcoes').emit('change');return arquivo;}
async function iniciar(){const fim=get('bf-importacao-gerar').emit('click'),pedido=pedidos.shift();assert(pedido);return {fim,pedido};}
async function concluir(pedido,fim,dados=revisao){pedido.resolve(dados);await fim;}
(async()=>{
  assert(!get('bf-correcoes'),'Não preparar revisão sem conferir a fonte');
  const arquivo=await conferir();
  assert(get('bf-correcoes'),'A fonte conferida deve permitir enviar o relatório corrigido');
  assert(get('bf-importacao-gerar').disabled);
  assert(alvo.textContent.includes('vazio')&&alvo.textContent.includes('manter')&&alvo.textContent.includes('ignorar'));
  assert(alvo.textContent.includes('justificativa')&&alvo.textContent.includes('originais'));
  await get('bf-importacao-gerar').emit('click');assert.strictEqual(chamadas.length,0);
  await selecionar('arquivo.xls');await get('bf-importacao-gerar').emit('click');assert.strictEqual(chamadas.length,0);
  await selecionar('arquivo.xlsx',21*1024*1024);await get('bf-importacao-gerar').emit('click');assert.strictEqual(chamadas.length,0);
  const correcoes=await selecionar();let atual=await iniciar();
  assert(get('bf-importacao-gerar').disabled);
  await get('bf-importacao-gerar').emit('click');assert.strictEqual(chamadas.length,1);
  assert.strictEqual(chamadas[0].url,'/api/clientes/base-fiscal/importacao/previa');
  assert.deepStrictEqual(chamadas[0].opcoes.body.itens.map(p=>p[0]),['arquivo','correcoes','hash_esperado']);
  assert.strictEqual(chamadas[0].opcoes.body.itens[0][1],arquivo);assert.strictEqual(chamadas[0].opcoes.body.itens[1][1],correcoes);
  assert.strictEqual(chamadas[0].opcoes.body.itens[2][1],fonte.hash_arquivo);
  await concluir(atual.pedido,atual.fim);
  assert(!get('bf-importacao-gerar').disabled);
  assert(get('bf-importacao-status').textContent.includes('Nenhum cadastro'));
  assert(alvo.textContent.includes('30/10/2026, 09:00:00 (horário de Salvador)'), 'Consulta em UTC deve aparecer no horário de Salvador');
  assert(!alvo.textContent.includes('2026-10-30T12:00:00'), 'Não mostrar ISO cru ao usuário');
  for(const tipo of tipos)assert.strictEqual(get('bf-importacao-total-'+tipo).textContent,'12');
  assert(get('bf-importacao-pagina').textContent.includes('1–25 de 60'));
  assert(get('bf-importacao-corpo').textContent.includes('<b>Proposta 0</b>'));
  assert(!elementos(get('bf-importacao-resultado')).some(e=>e.tagName==='b'));
  assert(alvo.textContent.includes('revalidada')&&alvo.textContent.includes('sem vínculo'));
  assert(!elementos(alvo).some(e=>e.tagName==='button'&&/^(Confirmar|Importar empresas|Gravar)/.test(e.textContent)));
  const detalhe=elementos(get('bf-importacao-corpo')).find(e=>e.tagName==='button');await detalhe.emit('click');
  assert(get('bf-importacao-corpo').textContent.includes('Original 0'));
  assert(get('bf-importacao-corpo').textContent.includes('H2'));
  assert(get('bf-importacao-corpo').textContent.includes('Preservar original'));
  await get('bf-importacao-proxima').emit('click');assert(get('bf-importacao-pagina').textContent.includes('26–50'));
  get('bf-importacao-filtro').value='conflito';await get('bf-importacao-filtro').emit('change');
  assert(get('bf-importacao-pagina').textContent.includes('1–12 de 12'));
  get('bf-importacao-busca').value='proposta 2<';await get('bf-importacao-busca').emit('input');
  assert(get('bf-importacao-pagina').textContent.includes('1–1 de 1'));
  const detalheCadastro=elementos(get('bf-importacao-corpo')).find(e=>e.tagName==='button');await detalheCadastro.emit('click');
  assert(get('bf-importacao-corpo').textContent.includes('Cadastro 2'));
  assert(get('bf-importacao-corpo').textContent.includes('revisão 3'));
  await get('bf-importacao-limpar-filtros').emit('click');assert(get('bf-importacao-pagina').textContent.includes('1–25 de 60'));
  assert.strictEqual(get('bf-importacao-total-conflito').textContent,'12','Filtros não alteram totais');

  // Proposta recusada não some da busca quando o valor efetivo ficou pendente.
  atual=await iniciar();
  const invalida={...revisao,cadastro_consultado_em:'data inválida',linhas:[{...revisao.linhas[3],
    proposto:{...revisao.linhas[3].proposto,documento:'documento a corrigir'},
    efetivo:{...revisao.linhas[3].efetivo,documento:''}}],
    contagens:{linhas:1,incluir:0,existente:0,conflito:0,pendente:1,ignorar:0,alteradas:1}};
  await concluir(atual.pedido,atual.fim,invalida);
  assert(alvo.textContent.includes('Horário da consulta cadastral indisponível.'), 'Data inválida deve ser explícita');
  assert(!alvo.textContent.includes('Invalid Date'));
  get('bf-importacao-busca').value='documento a corrigir';await get('bf-importacao-busca').emit('input');
  assert(get('bf-importacao-pagina').textContent.includes('1–1 de 1'),'Busca deve localizar a proposta inválida, sem depender do efetivo');

  atual=await iniciar();atual.pedido.reject(new Error('<b>Arquivo recusado</b>'));await atual.fim;
  assert(get('bf-importacao-status').textContent.includes('<b>Arquivo recusado</b>'));
  assert.strictEqual(get('bf-importacao-resultado').textContent,'');assert(!get('bf-importacao-gerar').disabled);
  atual=await iniciar();await concluir(atual.pedido,atual.fim,{...revisao,somente_leitura:false});
  assert.strictEqual(get('bf-importacao-resultado').textContent,'');
  atual=await iniciar();await concluir(atual.pedido,atual.fim,{...revisao,hash_arquivo:'f'.repeat(64)});
  assert.strictEqual(get('bf-importacao-resultado').textContent,'');

  // Troca de correções durante HTTP: nem interpretar a resposta antiga.
  atual=await iniciar();await selecionar('outras.xlsx');
  await concluir(atual.pedido,atual.fim);assert.strictEqual(get('bf-importacao-resultado').textContent,'');
  // api() inclui a leitura JSON: nova consulta conclui antes da anterior.
  atual=await iniciar();
  await selecionar('terceira.xlsx');let nova=await iniciar();await concluir(nova.pedido,nova.fim);
  await concluir(atual.pedido,atual.fim,{...revisao,avisos:['resposta antiga privada']});
  assert(!alvo.textContent.includes('resposta antiga privada'));
  assert(get('bf-importacao-resultado').textContent.includes('60'));
  // Fonte substituída e limpeza invalidam tudo.
  atual=await iniciar();get('bf-arquivo').files=[{name:'nova.xlsx',size:100}];await get('bf-arquivo').emit('change');
  atual.pedido.reject(new Error('erro antigo privado'));await atual.fim;assert.strictEqual(get('bf-resultado').textContent,'');
  await conferir();await selecionar();atual=await iniciar();await get('bf-limpar').emit('click');
  await concluir(atual.pedido,atual.fim);assert.strictEqual(get('bf-resultado').textContent,'');

  for(const perda of ['identidade','aba.clientes','clientes.importar','sessao']){
    permissoes=new Set(['aba.clientes','clientes.importar']);await conferir();await selecionar();atual=await iniciar();
    if(perda==='identidade')ctx.Sessao.usuario={id:2};else if(perda==='sessao')doc.dispatchEvent({type:'sessao:encerrada'});else permissoes.delete(perda);
    await concluir(atual.pedido,atual.fim);assert.strictEqual(get('bf-resultado').textContent,'',perda);
  }
  permissoes=new Set(['aba.clientes','clientes.importar']);await conferir();await selecionar();
  ctx.Sessao.usuario={id:99};let antes=chamadas.length;await get('bf-importacao-gerar').emit('click');
  assert.strictEqual(chamadas.length,antes);assert.strictEqual(get('bf-resultado').textContent,'');
  await conferir();await selecionar();atual=await iniciar();await conferir();
  atual.pedido.reject(new Error('erro antigo de revisão'));await atual.fim;assert(!alvo.textContent.includes('erro antigo de revisão'));
  await selecionar();atual=await iniciar();const erro=new Error('Fonte divergente');erro.codigo='BASE_FISCAL_DIVERGENTE';
  atual.pedido.reject(erro);await atual.fim;assert.strictEqual(get('bf-resultado').textContent,'');
  console.log('OK - importação Fiscal UI: prévia sem carga, revisão completa, filtros, segurança de texto e respostas obsoletas');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    return subprocess.run([node, '-e', script], cwd=raiz, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
