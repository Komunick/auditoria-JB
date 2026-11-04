# Validação da correção do menu lateral

Data: 04/11/2026. Ambiente local, com dados fictícios.

## Problema e correção

Em janelas baixas, com as 13 abas disponíveis para o administrador, o conteúdo
da navegação ultrapassava sua área e sobrepunha Administração ao botão
Minimizar o menu. O problema foi reproduzido antes da alteração em 1280 × 738 px.

A navegação agora tem rolagem própria. A marca, o botão e os grupos de abas
mantêm sua altura, reservando espaço para o rodapé. O ajuste contém quatro
linhas de CSS no bloco desktop, acima de 920,02 px. O layout móvel continua
usando as regras existentes.

## Validação no navegador

| Janela | Casos verificados | Resultado |
|---|---|---|
| 1280 × 738 px | Menu aberto e recolhido; Administração e botão de minimizar/expandir | Aprovado |
| 1024 × 600 px | Menu aberto e recolhido; acesso às abas com rolagem | Aprovado |
| 960 × 480 px | Menu aberto e recolhido; acesso às abas com rolagem | Aprovado |
| 920 × 600 px | Layout móvel, abas acessíveis e botão de minimizar oculto | Aprovado |
| 390 × 844 px | Layout móvel, abas sem corte horizontal e Administração acessível | Aprovado |

No caso inicial, a interseção das caixas dos controles era de 3.958,25 px².
Após a correção, com Administração visível na área rolável, a interseção é
zero e o centro do botão de minimizar corresponde ao controle correto.

Administração abre sua tela. Minimizar e expandir preservam a aba atual. As
13 abas foram percorridas por teclado nos modos aberto e recolhido, com foco
visível e rolagem automática. Tab, Shift+Tab, Enter e Espaço foram conferidos.

As evidências de navegador foram coletadas durante a implementação com o mesmo
patch de CSS. Capturas e medições ficam em `tmp/validacao-menu-20261104`, na
pasta de trabalho local e fora do Git. Preview usado: `http://127.0.0.1:8626/`.

## Conferência para publicação

O branch foi criado a partir de `origin/dev`, em checkout separado. O diff
inclui somente `webui/estilo.css` e este documento; as alterações locais do
semáforo não foram incluídas.

No checkout isolado, passaram `tests/test_central_ui.py` e
`tests/test_tarefas_filtros_ui.py`, ambos com Node e dados sintéticos, além de
`git diff --check`. Esses testes complementam a conferência de layout no
navegador; não substituem suas medições visuais. Revisão independente do CSS e
das evidências sem achados bloqueantes.

Não há mudanças de JavaScript, backend, permissões, dados ou dependências.
A validação ocorreu apenas localmente; a correção ainda não foi implantada.
