"""Revisão Fiscal no navegador: DOM seguro, filtros e isolamento de sessão."""
import pathlib
import shutil
import subprocess


def main():
    raiz = pathlib.Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        print("PULADO - base Fiscal UI: Node não instalado")
        return 0
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const doc = {listeners: {},
  addEventListener(tipo, fn) { (this.listeners[tipo] ||= []).push(fn); },
  dispatchEvent(e) { for (const fn of this.listeners[e.type] || []) fn(e); },
  createElement(tag) {
    return {tagName: tag, children: [], attributes: {}, listeners: {}, value: '', files: [],
      className: '', disabled: false, hidden: false, _texto: '',
      set textContent(v) { this._texto = String(v ?? ''); this.children = []; },
      get textContent() { return this._texto + this.children.map(e => e.textContent).join(''); },
      set innerHTML(v) { throw Error('Conteúdo HTML não permitido na prévia Fiscal'); },
      append(...itens) { for (const item of itens) { this.children.push(item); item.parent = this; } },
      appendChild(item) { this.append(item); return item; },
      replaceChildren(...itens) { this.textContent = ''; this.append(...itens); },
      setAttribute(nome, valor) { this.attributes[nome] = String(valor); },
      addEventListener(tipo, fn) { (this.listeners[tipo] ||= []).push(fn); },
      async emit(tipo) { for (const fn of this.listeners[tipo] || []) await fn({preventDefault() {}, target: this}); },
      focus() { doc.activeElement = this; },
      classList: {add() {}, remove() {}, toggle() {}},
    };
  }};
const elementos = e => [e, ...e.children.flatMap(elementos)];
const alvo = doc.createElement('section');
const get = id => elementos(alvo).find(e => e.id === id);
let permitido = true, chamadas = [], pendentes = [];
const ctx = {document: doc, console, Abas: {registrar() {}},
  Sessao: {usuario: {id: 1}, pode() { return permitido; }},
  apiUpload(url, arquivo) { chamadas.push({url, arquivo}); return new Promise((resolve,reject) => pendentes.push({resolve,reject})); }};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('webui/clientes.js', 'utf8'), ctx);
const run = code => vm.runInContext(code, ctx);
ctx.alvo = alvo;
const linhas = Array.from({length:360}, (_, i) => ({id:`${i < 350 ? 1 : 2}:${i+3}`,
  aba: i < 350 ? 'Fiscal sintético' : 'ZERADAS', linha:i+3,
  nome: i === 0 ? '<img src=x onerror=alert(1)>' : `Empresa sintética ${i+1}`,
  documento:'12345678000195', documento_informado:'12.345.678/0001-95', documento_status:'valido',
  regime:'Simples Nacional', regime_informado:'SIMPLES', responsavel_fiscal_informado:'Pessoa Fiscal',
  contato_nome:'Contato separado', sem_movimento:i>=350 ? true : null, duplicado:i<2,
  duplicado_em:i===0 ? ['1:4'] : [], pendencias:i<2 ? ['CNPJ repetido'] : [], oculta:false, aba_oculta:false,
  origem:{responsavel_fiscal:{celula:`B${i+3}`,celula_origem:`B${i+3}`,valor_informado:'Pessoa Fiscal',formato:'General',propagado:false},
    contato_nome:{celula:`D${i+3}`,celula_origem:'D3',valor_informado:'Contato separado',formato:'General',propagado:i>0,intervalo_mesclado:'D3:D362'}}}));
const previa = {somente_leitura:true,nome_arquivo:'base-sintetica.xlsx',hash_arquivo:'a'.repeat(64),
  formato:'base_fiscal_v1',avisos:['<script>aviso</script>'],abas:[{nome:'Fiscal sintético',tipo:'principal',linha_cabecalho:2,total:350,oculta:false},{nome:'ZERADAS',tipo:'zeradas',linha_cabecalho:2,total:10,oculta:false}],
  contagens:{linhas:360,cnpjs_distintos:359,documentos_validos:360,documentos_pendentes:0,grupos_duplicados:1,linhas_duplicadas:2,sem_movimento:10,com_pendencias:2},linhas};
ctx.linhas = linhas;
assert.strictEqual(run('BaseFiscalUI.selecionar(linhas,{texto:"FISCAL",situacao:"duplicados",aba:""}).length'),2);
assert.strictEqual(run('BaseFiscalUI.selecionar(linhas,{texto:"sintetica 360",situacao:"sem_movimento",aba:"ZERADAS"}).length'),1);
assert.strictEqual(run('BaseFiscalUI.selecionar(linhas,{texto:"Contato separado",situacao:"",aba:""}).length'),360);
assert.strictEqual(run('BaseFiscalUI.selecionar(linhas,{texto:"12345678000195",situacao:"",aba:""}).length'),360);
assert.strictEqual(run('BaseFiscalUI.selecionar([{documento_status:"formula"},{documento_status:"zero_inicial_recuperado"}],{situacao:"documentos"}).length'),1);
assert.strictEqual(run('BaseFiscalUI.selecionar([{regime:""},{regime:"Lucro Real"},{regime:"",campos_ausentes_no_layout:["regime"]}],{situacao:"sem_regime"}).length'),1);
assert.strictEqual(run('BaseFiscalUI.selecionar([{responsavel_fiscal_informado:""},{responsavel_fiscal_informado:"Teste"},{responsavel_fiscal_informado:"",campos_ausentes_no_layout:["responsavel_fiscal"]}],{situacao:"sem_responsavel"}).length'),1);
run('BaseFiscalUI.montar(alvo)');
async function enviar(nome='base.xlsx') {
  get('bf-arquivo').files = [{name:nome,size:100}];
  await get('bf-arquivo').emit('change');
  return {terminar:get('bf-ler').emit('click')};
}
(async () => {
  assert(alvo.textContent.includes('Sem gravação'));
  assert.strictEqual(chamadas.length,0);
  let pedido = await enviar();
  assert.strictEqual(chamadas[0].url,'/api/clientes/base-fiscal/previa');
  assert(get('bf-status').textContent.includes('Lendo'));
  pendentes.shift().resolve(previa); await pedido.terminar;
  assert.strictEqual(elementos(get('bf-corpo')).filter(e => e.attributes['data-registro']).length,25);
  assert.strictEqual(get('bf-total-linhas').textContent,'360');
  assert.strictEqual(get('bf-total-cnpjs_distintos').textContent,'359');
  assert(alvo.textContent.includes('<img src=x onerror=alert(1)>'));
  assert(alvo.textContent.includes('<script>aviso</script>'));
  assert(!elementos(alvo).some(e => ['img','script'].includes(e.tagName)));
  assert(alvo.textContent.includes('Pessoa Fiscal') && alvo.textContent.includes('Contato separado'));
  const origem = elementos(get('bf-corpo')).find(e => e.attributes['aria-expanded'] === 'false');
  assert(origem); await origem.emit('click');
  assert.strictEqual(origem.attributes['aria-expanded'],'true');
  assert(alvo.textContent.includes('B3') && alvo.textContent.includes('D3:D362'));
  assert(alvo.textContent.includes('Fiscal sintético · linha 4'));
  get('bf-tamanho').value='50'; await get('bf-tamanho').emit('change');
  assert.strictEqual(elementos(get('bf-corpo')).filter(e => e.attributes['data-registro']).length,50);
  for(let i=0;i<7;i++) await get('bf-proxima').emit('click');
  assert(get('bf-pagina').textContent.includes('351–360 de 360'));
  assert.strictEqual(get('bf-proxima').disabled,true);
  get('bf-situacao').value='sem_movimento'; await get('bf-situacao').emit('change');
  assert(get('bf-pagina').textContent.includes('1–10 de 10'));
  assert.strictEqual(get('bf-total-linhas').textContent,'360');
  get('bf-busca').value='não existe'; await get('bf-busca').emit('input');
  assert(get('bf-corpo').textContent.includes('Nenhum registro corresponde'));
  assert.strictEqual(get('bf-proxima').disabled,true);
  await get('bf-limpar-filtros').emit('click');
  assert(get('bf-pagina').textContent.includes('1–50 de 360'));
  // Campos inexistentes em ZERADAS nao sao dados faltantes nem pendencias.
  pedido = await enviar('zeradas.xlsx');
  const zerada = {...linhas[350], regime:'', regime_informado:'', responsavel_fiscal_informado:'', contato_nome:'',
    campos_ausentes_no_layout:['contato_nome','regime','responsavel_fiscal'], origem:{}, pendencias:[]};
  pendentes.shift().resolve({...previa,linhas:[zerada],contagens:{...previa.contagens,linhas:1,com_pendencias:0}});
  await pedido.terminar;
  assert.strictEqual(elementos(get('bf-corpo')).filter(e => e.textContent === 'Coluna ausente no layout').length,3);
  assert(get('bf-corpo').textContent.includes('Sem pendências de leitura'));
  for (const situacao of ['sem_responsavel','sem_regime','pendencias']) {
    get('bf-situacao').value=situacao; await get('bf-situacao').emit('change');
    assert(get('bf-corpo').textContent.includes('Nenhum registro corresponde'));
  }
  // O arquivo novo invalida sucesso e erro atrasados; nenhum contador anterior sobrevive.
  pedido = await enviar('antiga.xlsx');
  get('bf-arquivo').files=[{name:'nova.xlsx',size:100}]; await get('bf-arquivo').emit('change');
  pendentes.shift().resolve(previa); await pedido.terminar;
  assert.strictEqual(get('bf-resultado').textContent,'');
  assert(!get('bf-status').textContent.includes('360'));
  pedido = await enviar();
  doc.dispatchEvent({type:'sessao:encerrada'});
  pendentes.shift().reject(new Error('erro privado atrasado')); await pedido.terminar;
  assert.strictEqual(get('bf-resultado').textContent,'');
  assert.strictEqual(get('bf-arquivo').value,'');
  assert(!alvo.textContent.includes('erro privado atrasado'));
  // Troca de identidade também impede pintar resultado, mesmo antes do evento.
  pedido=await enviar(); ctx.Sessao.usuario={id:2};
  pendentes.shift().resolve(previa); await pedido.terminar;
  assert.strictEqual(get('bf-resultado').textContent,'');
  pedido=await enviar(); pendentes.shift().reject(new Error('<b>Arquivo inválido</b>')); await pedido.terminar;
  assert(get('bf-status').textContent.includes('<b>Arquivo inválido</b>'));
  assert.strictEqual(get('bf-resultado').textContent,'');
  pedido=await enviar(); pendentes.shift().resolve({...previa,linhas:[],contagens:{...previa.contagens,linhas:0}}); await pedido.terminar;
  assert(get('bf-corpo').textContent.includes('Nenhum registro no arquivo'));
  const antes=chamadas.length; permitido=false;
  pedido=await enviar(); await pedido.terminar;
  assert.strictEqual(chamadas.length,antes);
  assert.strictEqual(get('bf-resultado').textContent,'');
  const oculto=doc.createElement('section'); ctx.oculto=oculto;
  run('BaseFiscalUI.montar(oculto)'); assert(!elementos(oculto).some(e => e.tagName==='input'));
  // Nenhuma persistência/rota de confirmação no módulo. Legados continuam registrados.
  const fonte=fs.readFileSync('webui/clientes.js','utf8');
  const modulo=fonte.slice(fonte.indexOf('const BaseFiscalUI'),fonte.indexOf('Abas.registrar("clientes"'));
  assert(!/localStorage|sessionStorage|\/confirmar|\.token\b|innerHTML/.test(modulo));
  assert(fonte.includes('"cli-imp-planilha-enviar").addEventListener("click", previaPlanilha)'));
  assert(fonte.includes('"cli-imp-coleta-enviar").addEventListener("click", previaColeta)'));
  const app=fs.readFileSync('webui/app.js','utf8');
  assert(app.includes('mostrarLogin() {\n    Sessao.definir(null);\n    document.dispatchEvent(new CustomEvent("sessao:encerrada"));') || app.includes('mostrarLogin() {\r\n    Sessao.definir(null);\r\n    document.dispatchEvent(new CustomEvent("sessao:encerrada"));'));
  assert.strictEqual((app.match(/if \(!novo.logado\) throw new Error\("Não foi possível confirmar a sessão\."\);/g)||[]).length,2);
  assert(!app.includes('Telas.mostrarApp(novo.usuario)'));
  // Executa a autenticação real com API substituída: só uma sessão confirmada
  // recarrega o documento; encerrar login limpa identidade e avisa os módulos.
  const elementosAuth = new Map(); let recargas = 0, encerramentos = 0;
  const authDoc = {...doc, listeners:{}, readyState:'complete',
    getElementById(id) { if(!elementosAuth.has(id)) elementosAuth.set(id,doc.createElement('div')); return elementosAuth.get(id); },
    querySelectorAll() { return []; }};
  authDoc.addEventListener('sessao:encerrada', () => encerramentos++);
  const auth = {document:authDoc,console,location:{reload() { recargas++; }},CustomEvent:class {constructor(type) {this.type=type;}}};
  vm.createContext(auth);
  vm.runInContext(app.slice(0,app.indexOf('document.getElementById("botao-sair")')),auth);
  vm.runInContext('Sessao.definir({id:7,permissoes:["aba.clientes"]}); Telas.mostrarLogin()',auth);
  assert.strictEqual(vm.runInContext('Sessao.usuario',auth),null);
  assert.strictEqual(vm.runInContext('Sessao.pode("aba.clientes")',auth),false);
  assert.strictEqual(encerramentos,1);
  auth.estado = {logado:false,precisa_bootstrap:false};
  vm.runInContext('Tema.iniciar=()=>{}; Lateral.iniciar=()=>{}; api=async(caminho)=>caminho==="/api/estado" ? estado : {}',auth);
  await vm.runInContext('iniciar()',auth);
  auth.estado={logado:true,usuario:{id:8}};
  await authDoc.getElementById('form-login').emit('submit');
  assert.strictEqual(recargas,1);
  await authDoc.getElementById('form-bootstrap').emit('submit');
  assert.strictEqual(recargas,2);
  auth.estado={logado:false};
  await authDoc.getElementById('form-login').emit('submit');
  assert.strictEqual(recargas,2);
  assert(authDoc.getElementById('login-erro').textContent.includes('confirmar a sessão'));
  console.log('OK - base Fiscal UI: revisão, texto seguro, paginação, sessão e legados');
})().catch(e => { console.error(e); process.exitCode=1; });
'''
    return subprocess.run([node, "-e", script], cwd=raiz, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
