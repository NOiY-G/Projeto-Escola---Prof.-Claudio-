"""Menu do topo: a mesma estrutura desenha o menu do computador e o do celular."""

from dataclasses import dataclass, field

from django.urls import reverse

from apps.financeiro.models import Parcela

from .services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO, PERFIL_INSTRUTOR


@dataclass
class Item:
    rotulo: str
    url: str
    # Prefixos de nomes de view (ex.: "catalogo:curso") em que o item fica destacado.
    ativo_em: tuple = ()
    ativo: bool = False
    contador: int = 0


@dataclass
class Grupo:
    rotulo: str
    itens: list = field(default_factory=list)

    @property
    def ativo(self):
        return any(item.ativo for item in self.itens)

    @property
    def contador(self):
        return sum(item.contador for item in self.itens)


def _estrutura(perfil):
    if perfil == PERFIL_ADMINISTRADOR:
        comprovantes = Parcela.objects.filter(status=Parcela.Status.EM_ANALISE).count()
        return [
            Item("Painel", reverse("contas:painel"), ("contas:painel",)),
            Grupo("Cadastros", [
                Item("Cursos", reverse("catalogo:curso_lista"), ("catalogo:curso",)),
                Item("Instrutores", reverse("catalogo:instrutor_lista"), ("catalogo:instrutor",)),
                Item("Alunos", reverse("alunos:aluno_lista"), ("alunos:",)),
            ]),
            Grupo("Turmas", [
                Item("Turmas", reverse("turmas:turma_lista"), ("turmas:turma", "matriculas:chamada", "certificados:concluir")),
                Item("Lista de espera", reverse("matriculas:lista_espera"), ("matriculas:lista_espera", "matriculas:matricula_nova")),
                Item("Feriados", reverse("turmas:feriados"), ("turmas:feriado",)),
            ]),
            Grupo("Financeiro", [
                Item("Pagamentos", reverse("financeiro:pagamentos"), ("financeiro:",)),
                Item("Comprovantes para conferir", reverse("financeiro:pagamentos") + "?ver=comprovantes", contador=comprovantes),
                Item("Relatório financeiro", reverse("relatorios:relatorio", args=["financeiro"])),
            ]),
            Item("Certificados", reverse("certificados:lista"), ("certificados:lista", "certificados:emitir")),
            Item("Relatórios", reverse("relatorios:inicio"), ("relatorios:",)),
        ]
    if perfil == PERFIL_INSTRUTOR:
        return [
            Item("Painel", reverse("contas:painel"), ("contas:painel",)),
            Item("Minhas turmas", reverse("turmas:turma_lista"), ("turmas:", "matriculas:chamada")),
        ]
    if perfil == PERFIL_ALUNO:
        return [
            Item("Painel", reverse("contas:painel"), ("contas:painel",)),
            Item("Minhas matrículas", reverse("matriculas:minhas_matriculas"), ("matriculas:minhas",)),
        ]
    return [Item("Painel", reverse("contas:painel"), ("contas:painel",))]


def montar_menu(request, perfil):
    estrutura = _estrutura(perfil)
    vista = getattr(getattr(request, "resolver_match", None), "view_name", "") or ""
    for entrada in estrutura:
        for item in getattr(entrada, "itens", [entrada]):
            item.ativo = any(vista.startswith(prefixo) for prefixo in item.ativo_em)
    return estrutura
