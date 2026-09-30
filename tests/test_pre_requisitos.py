"""Pré-requisitos do curso na matrícula (concluído aqui ou feito em outra escola)."""

import datetime

import pytest
from django.urls import reverse

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso
from apps.matriculas import services as matriculas
from apps.matriculas.models import Matricula
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db


@pytest.fixture
def excel(curso):
    excel = Curso.objects.create(nome="Excel", duracao_meses=2)
    excel.pre_requisitos.set([curso])  # Excel pede Informática Básica
    return excel


def _turma(curso, instrutor, codigo, dias="seg,qua", **extra):
    dados = dict(
        curso=curso, instrutor=instrutor, codigo=codigo,
        data_inicio=datetime.date(2026, 10, 5), data_fim=datetime.date(2026, 12, 4),
        dias_semana=dias, hora_inicio=datetime.time(8), hora_fim=datetime.time(10), vagas=10,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )
    dados.update(extra)
    return Turma.objects.create(**dados)


@pytest.fixture
def turma_excel(excel, instrutor):
    return _turma(excel, instrutor, "EXC-01")


def _concluir(aluno, curso, instrutor):
    turma = _turma(curso, instrutor, f"OLD-{aluno.pk}", dias="sab", status=Turma.Status.CONCLUIDA)
    return Matricula.objects.create(aluno=aluno, turma=turma, status=Matricula.Status.CONCLUIDA)


def test_sem_pre_requisito_concluido_a_matricula_e_recusada(aluno, turma_excel):
    assert matriculas.pre_requisitos_pendentes(aluno, turma_excel.curso) == [turma_excel.curso.pre_requisitos.get()]
    with pytest.raises(matriculas.MatriculaErro, match="não concluiu o pré-requisito \\(Informática Básica\\)"):
        matriculas.matricular(aluno, turma_excel)
    assert not Matricula.objects.filter(turma=turma_excel).exists()


def test_quem_concluiu_o_pre_requisito_aqui_matricula_normalmente(aluno, curso, instrutor, turma_excel):
    _concluir(aluno, curso, instrutor)
    matricula = matriculas.matricular(aluno, turma_excel)
    assert matricula.status == Matricula.Status.ATIVA and not matricula.pre_requisito_outra_escola


def test_desistente_do_pre_requisito_nao_conta(aluno, curso, instrutor, turma_excel):
    Matricula.objects.filter(pk=_concluir(aluno, curso, instrutor).pk).update(status=Matricula.Status.DESISTENTE)
    assert matriculas.pre_requisitos_pendentes(aluno, turma_excel.curso)


def test_pre_requisito_feito_em_outra_escola(aluno, turma_excel):
    matricula = matriculas.matricular(aluno, turma_excel, pre_requisito_outra_escola=True)
    assert matricula.status == Matricula.Status.ATIVA and matricula.pre_requisito_outra_escola


def test_curso_que_nao_aceita_outra_escola(aluno, excel, turma_excel):
    excel.aceita_outra_escola = False
    excel.save()
    with pytest.raises(matriculas.MatriculaErro, match="não aceita pré-requisito feito em outra escola"):
        matriculas.matricular(aluno, turma_excel, pre_requisito_outra_escola=True)


def test_curso_sem_pre_requisito_ignora_a_opcao(aluno, turma):
    turma.status = Turma.Status.INSCRICOES_ABERTAS
    turma.save()
    matricula = matriculas.matricular(aluno, turma, pre_requisito_outra_escola=True)
    assert not matricula.pre_requisito_outra_escola


def test_matricula_pela_tela_com_outra_escola(client, usuario_admin, aluno, turma_excel):
    client.force_login(usuario_admin)
    url = reverse("matriculas:matricula_nova")
    resposta = client.post(url, {"aluno": aluno.pk, "turma": turma_excel.pk, "desconto": "0"})
    assert "não concluiu o pré-requisito" in resposta.content.decode()
    client.post(url, {"aluno": aluno.pk, "turma": turma_excel.pk, "pre_requisito_outra_escola": "on"})
    matricula = Matricula.objects.get(turma=turma_excel)
    assert matricula.pre_requisito_outra_escola
    detalhe = client.get(reverse("turmas:turma_detalhe", args=[turma_excel.pk])).content.decode()
    assert "pré-requisito em outra escola" in detalhe


def test_resumo_da_matricula_mostra_o_pre_requisito(client, usuario_admin, aluno, curso, instrutor, turma_excel):
    client.force_login(usuario_admin)
    url = reverse("matriculas:matricula_resumo_turma")
    conteudo = client.get(url, {"turma": turma_excel.pk, "aluno": aluno.pk}).content.decode()
    assert "Pré-requisito: Informática Básica" in conteudo
    assert f"{aluno.nome} não concluiu Informática Básica aqui" in conteudo
    _concluir(aluno, curso, instrutor)
    conteudo = client.get(url, {"turma": turma_excel.pk, "aluno": aluno.pk}).content.decode()
    assert f"{aluno.nome} já concluiu" in conteudo


def test_aluno_sem_cadastro_no_resumo(client, usuario_admin, turma_excel):
    client.force_login(usuario_admin)
    conteudo = client.get(
        reverse("matriculas:matricula_resumo_turma"), {"turma": turma_excel.pk, "aluno": "x"}
    ).content.decode()
    assert "Pré-requisito: Informática Básica" in conteudo and "não concluiu" not in conteudo
    assert Aluno.objects.count() == 0
