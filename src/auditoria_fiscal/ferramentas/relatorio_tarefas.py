"""Exportação da lista autorizada: texto seguro e autoria preservada."""
import io
from openpyxl import Workbook
from ..core.planilha_segura import escrever_cabecalho, escrever_texto

CAMPOS = (
    ('id', 'Código'), ('cliente_nome', 'Cliente'), ('setor_nome', 'Setor'),
    ('titulo', 'Tarefa'), ('competencia', 'Competência'), ('inicio', 'Início'),
    ('vencimento', 'Vencimento'), ('situacao', 'Situação'),
    ('responsavel_nome', 'Responsável titular'), ('responsavel_efetivo_nome', 'Responsável hoje'),
    ('concluida_em', 'Concluída em'), ('concluida_nome', 'Concluída por'),
    ('conferida_em', 'Conferida em'), ('conferida_nome', 'Conferida por'),
    ('conferida_substituindo', 'Substituindo usuário'), ('fora_do_prazo', 'Fora do prazo'),
)


def gerar_relatorio(tarefas):
    livro = Workbook()
    aba = livro.active
    aba.title = 'Tarefas e prazos'
    escrever_cabecalho(aba, [titulo for _, titulo in CAMPOS])
    for linha, tarefa in enumerate(tarefas, 2):
        for coluna, (chave, _) in enumerate(CAMPOS, 1):
            valor = tarefa.get(chave, '')
            if chave in ('concluida_nome', 'conferida_nome') and not valor:
                valor = tarefa.get(chave.replace('_nome', '_por'), '')
            if chave == 'fora_do_prazo':
                valor = 'Sim' if valor else 'Não'
            escrever_texto(aba, linha, coluna, valor)
    aba.auto_filter.ref = aba.dimensions
    saida = io.BytesIO()
    livro.save(saida)
    livro.close()
    return saida.getvalue()
