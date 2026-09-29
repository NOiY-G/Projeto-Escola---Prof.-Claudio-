import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso
from apps.matriculas.models import Matricula
from apps.relatorios import services
from apps.turmas.models import Aula, Turma

pytestmark = pytest.mark.django_db

S = Matricula.Status
HOJE = timezone.localdate()
CPFS = [
    "11144477735", "39053344705", "82286187041", "71428793860", "45317828791",
    "52998224725", "86288366757", "15350946056", "48722315020", "07068093868",
]


@pytest.fixture
def cenario(curso, instrutor):
    """Informática Básica: T1 (2025, concluída) e T2 (em andamento, 4 vagas).
    Excel: T3 (inscrições abertas, 10 vagas) e T4 (cancelada).
    """
    excel = Curso.objects.create(nome="Excel", carga_horaria=20)
    alunos = [
        Aluno.objects.create(nome=f"Aluno {i:02d}", cpf=cpf, data_nascimento=datetime.date(2000, 1, 1))
        for i, cpf in enumerate(CPFS, start=1)
    ]

    def turma(codigo, curso_, status, vagas, ano=2026):
        return Turma.objects.create(
            curso=curso_, instrutor=instrutor, codigo=codigo, status=status, vagas=vagas,
            data_inicio=datetime.date(ano, 3, 2), data_fim=datetime.date(ano, 5, 29),
            dias_semana="seg,qua", hora_inicio=datetime.time(8), hora_fim=datetime.time(10),
        )

    t1 = turma("INF-2025-01", curso, Turma.Status.CONCLUIDA, 5, ano=2025)
    t2 = turma("INF-2026-01", curso, Turma.Status.EM_ANDAMENTO, 4)
    t3 = turma("EXC-2026-01", excel, Turma.Status.INSCRICOES_ABERTAS, 10)
    t4 = turma("EXC-2026-02", excel, Turma.Status.CANCELADA, 10)

    antigo = timezone.now() - datetime.timedelta(days=30)
    distribuicao = {
        t1: [S.CONCLUIDA, S.CONCLUIDA, S.CONCLUIDA, S.DESISTENTE, S.CANCELADA],
        t2: [S.ATIVA, S.ATIVA, S.DESISTENTE, S.LISTA_ESPERA],
        t3: [S.ATIVA, S.ATIVA, S.ATIVA],
        t4: [S.CANCELADA, S.CANCELADA],
    }
    for t, lista in distribuicao.items():
        for aluno, status in zip(alunos, lista):
            # T3 são as matrículas desta semana; o resto é antigo.
            data = timezone.now() if t == t3 else antigo
            Matricula.objects.create(aluno=aluno, turma=t, status=status, data=data)
    Aula.objects.create(turma=t2, data=HOJE)
    Aula.objects.create(turma=t4, data=HOJE)  # turma cancelada: não conta
    return {"t1": t1, "t2": t2, "t3": t3, "t4": t4, "excel": excel}


def _por(linhas, chave, valor):
    return next(l for l in linhas if l[chave] == valor)


# Alunos por curso


def test_alunos_por_curso(cenario):
    linhas = services.alunos_por_curso(services.turmas_filtradas())
    assert [l["curso"] for l in linhas] == ["Excel", "Informática Básica"]
    info = _por(linhas, "curso", "Informática Básica")
    # Alunos 01-04 em T1 (05 cancelado) e 01-04 em T2: 4 alunos distintos.
    assert info == {
        "curso": "Informática Básica", "turmas": 2, "alunos": 4, "ativas": 2, "espera": 1,
        "concluidas": 3, "desistentes": 2, "canceladas": 1,
    }
    excel = _por(linhas, "curso", "Excel")
    assert (excel["turmas"], excel["alunos"], excel["ativas"], excel["canceladas"]) == (2, 3, 3, 2)


def test_filtros_por_ano_e_curso(cenario):
    so_2025 = services.alunos_por_curso(services.turmas_filtradas(ano=2025))
    assert so_2025 == [
        {"curso": "Informática Básica", "turmas": 1, "alunos": 4, "ativas": 0, "espera": 0,
         "concluidas": 3, "desistentes": 1, "canceladas": 1}
    ]
    so_excel = services.alunos_por_curso(services.turmas_filtradas(curso_id=cenario["excel"].pk))
    assert [l["curso"] for l in so_excel] == ["Excel"]
    assert services.anos_disponiveis() == [2026, 2025]


# Conclusão e evasão


def test_conclusao_e_evasao(cenario):
    linhas, total = services.conclusao_e_evasao(services.turmas_filtradas())
    assert "EXC-2026-02" not in [l["turma"] for l in linhas]  # cancelada fica de fora

    t1 = _por(linhas, "turma", "INF-2025-01")
    assert (t1["taxa_conclusao"], t1["taxa_evasao"]) == (75.0, 25.0)

    t2 = _por(linhas, "turma", "INF-2026-01")
    # Turma em andamento não tem taxa de conclusão; evasão = 1 ÷ (2 + 0 + 1).
    assert (t2["taxa_conclusao"], t2["taxa_evasao"]) == (None, 33.3)

    t3 = _por(linhas, "turma", "EXC-2026-01")
    assert (t3["taxa_conclusao"], t3["taxa_evasao"]) == (None, 0.0)

    # Total: conclusão só das turmas concluídas (3 ÷ 4); evasão 2 ÷ (5 ativas + 3 + 2).
    assert total["taxa_conclusao"] == 75.0
    assert total["taxa_evasao"] == 20.0
    assert (total["ativas"], total["concluidas"], total["desistentes"]) == (5, 3, 2)


def test_taxas_sem_dados_ficam_vazias(curso, instrutor):
    Turma.objects.create(
        curso=curso, instrutor=instrutor, codigo="X", status=Turma.Status.CONCLUIDA, vagas=5,
        data_inicio=HOJE, data_fim=HOJE, dias_semana="seg",
        hora_inicio=datetime.time(8), hora_fim=datetime.time(9),
    )
    linhas, total = services.conclusao_e_evasao(services.turmas_filtradas())
    assert (linhas[0]["taxa_conclusao"], linhas[0]["taxa_evasao"]) == (None, None)
    assert total["taxa_conclusao"] is None


# Ocupação


def test_ocupacao(cenario):
    linhas = services.ocupacao(services.turmas_filtradas())
    # Só turmas não encerradas, por data de início e depois código.
    assert [l["turma"] for l in linhas] == ["EXC-2026-01", "INF-2026-01"]
    t2 = _por(linhas, "turma", "INF-2026-01")
    assert (t2["vagas"], t2["ocupadas"], t2["livres"], t2["espera"], t2["ocupacao"]) == (4, 2, 2, 1, 50.0)
    t3 = _por(linhas, "turma", "EXC-2026-01")
    assert (t3["ocupadas"], t3["livres"], t3["ocupacao"]) == (3, 7, 30.0)


def test_barra_da_ocupacao_limitada_a_100(cenario):
    t3 = cenario["t3"]
    t3.vagas = 2  # vagas reduzidas depois das matrículas
    t3.save()
    linha = _por(services.ocupacao(services.turmas_filtradas()), "turma", "EXC-2026-01")
    assert (linha["ocupacao"], linha["barra"], linha["livres"]) == (150.0, 100, 0)


# Painel


def test_numeros_do_painel(cenario):
    numeros = services.numeros_do_painel()
    assert numeros.turmas_em_andamento == 1
    assert numeros.vagas_livres == 7  # só turmas com inscrições abertas (T3)
    assert numeros.na_fila == 1
    assert numeros.matriculas_7_dias == 3
    assert numeros.aulas_hoje == 1  # a aula da turma cancelada não conta
    assert len(numeros.recentes) == 5
    assert all(m.turma == cenario["t3"] for m in numeros.recentes[:3])


def test_painel_do_administrador(client, usuario_admin, cenario):
    client.force_login(usuario_admin)
    conteudo = client.get(reverse("contas:painel")).content.decode()
    assert "Turmas em andamento" in conteudo and "Vagas livres" in conteudo
    assert "Matrículas recentes" in conteudo and "EXC-2026-01" in conteudo


# CSV


def test_gerar_csv_formato_brasileiro():
    conteudo = services.gerar_csv(
        [("nome", "Nome"), ("taxa", "Taxa (%)"), ("n", "Qtd")],
        [{"nome": "Informática; Básica", "taxa": 66.7, "n": 3}, {"nome": "Excel", "taxa": None, "n": 0}],
    )
    assert conteudo.startswith("﻿")
    linhas = conteudo.lstrip("﻿").splitlines()
    assert linhas == ["Nome;Taxa (%);Qtd", '"Informática; Básica";66,7;3', "Excel;;0"]


def test_exportar_csv_respeita_filtros(client, usuario_admin, cenario):
    client.force_login(usuario_admin)
    resposta = client.get(reverse("relatorios:csv", args=["conclusao-evasao"]), {"ano": "2026"})
    assert resposta["Content-Type"] == "text/csv; charset=utf-8"
    assert 'filename="conclusao-evasao_2026_' in resposta["Content-Disposition"]
    linhas = resposta.content.decode("utf-8-sig").splitlines()
    assert linhas[0] == "Turma;Curso;Situação;Ativas;Concluídas;Desistentes;Conclusão;Evasão"
    assert "INF-2025-01" not in resposta.content.decode()
    assert any(l.startswith("INF-2026-01;Informática Básica;Em andamento;2;0;1;;33,3") for l in linhas)
    assert linhas[-1].startswith("Total;")


@pytest.mark.parametrize("slug", ["alunos-por-curso", "conclusao-evasao", "ocupacao"])
def test_telas_dos_relatorios(client, usuario_admin, cenario, slug):
    client.force_login(usuario_admin)
    resposta = client.get(reverse("relatorios:relatorio", args=[slug]), {"curso": cenario["excel"].pk})
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Exportar CSV" in conteudo
    assert f"/relatorios/{slug}/csv/?curso={cenario['excel'].pk}" in conteudo
    assert "Informática Básica" not in conteudo.split("<table")[1]


def test_tela_de_ocupacao_mostra_medidor(client, usuario_admin, cenario):
    client.force_login(usuario_admin)
    conteudo = client.get(reverse("relatorios:relatorio", args=["ocupacao"])).content.decode()
    assert "width: 50.0%" in conteudo and "width: 30.0%" in conteudo
    assert "3 de 10 vagas" in conteudo


def test_relatorio_inexistente(client, usuario_admin):
    client.force_login(usuario_admin)
    assert client.get("/relatorios/nao-existe/").status_code == 404


def test_relatorios_so_para_administrador(client, usuario_instrutor, usuario_aluno):
    url = reverse("relatorios:relatorio", args=["ocupacao"])
    assert client.get(url).status_code == 302
    for usuario in (usuario_instrutor, usuario_aluno):
        client.force_login(usuario)
        assert client.get(url).status_code == 403
        assert client.get(reverse("relatorios:csv", args=["ocupacao"])).status_code == 403
