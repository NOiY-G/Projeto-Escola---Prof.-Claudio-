import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.alunos.models import Aluno
from apps.alunos.validators import cpf_valido, mascarar_cpf
from apps.catalogo.models import Curso
from apps.certificados.models import Certificado
from apps.matriculas.models import Frequencia, Matricula
from apps.turmas.models import Aula, Turma

pytestmark = pytest.mark.django_db


def test_curso_padroes(curso):
    assert curso.frequencia_minima == 75
    assert curso.ativo
    assert curso.gratuito


def test_curso_nome_unico(curso):
    with pytest.raises(IntegrityError):
        Curso.objects.create(nome="Informática Básica", carga_horaria=10)


def test_curso_carga_horaria_positiva():
    with pytest.raises(IntegrityError):
        Curso.objects.create(nome="Excel", carga_horaria=0)


def test_turma_vagas_positivas(turma):
    turma.vagas = 0
    with pytest.raises(ValidationError):
        turma.full_clean()


@pytest.mark.parametrize("dias", ["", "seg,xyz", "segunda"])
def test_turma_dias_semana_invalidos(turma, dias):
    turma.dias_semana = dias
    with pytest.raises(ValidationError):
        turma.full_clean()


def test_turma_dias_semana_lista(turma):
    assert turma.dias_semana_lista == ["seg", "qua"]


def test_turma_periodo_e_horario_invalidos(turma):
    turma.data_fim = turma.data_inicio - datetime.timedelta(days=1)
    turma.hora_fim = turma.hora_inicio
    with pytest.raises(ValidationError) as erro:
        turma.full_clean()
    assert {"data_fim", "hora_fim"} <= set(erro.value.message_dict)


def test_turma_status_padrao(curso, instrutor):
    turma = Turma(curso=curso, instrutor=instrutor, codigo="X")
    assert turma.status == Turma.Status.PLANEJADA


@pytest.mark.parametrize(
    "cpf,valido",
    [
        ("529.982.247-25", True),
        ("52998224725", True),
        ("529.982.247-24", False),
        ("111.111.111-11", False),
        ("123", False),
    ],
)
def test_validacao_cpf(cpf, valido):
    assert cpf_valido(cpf) is valido


def test_aluno_cpf_guardado_sem_mascara_e_unico(aluno):
    assert aluno.cpf == "52998224725"
    assert aluno.cpf_formatado == "529.982.247-25"
    with pytest.raises(IntegrityError):
        Aluno.objects.create(nome="Outro", cpf="52998224725", data_nascimento=datetime.date(1990, 1, 1))


def test_aluno_cpf_invalido_rejeitado():
    aluno = Aluno(nome="X", cpf="12345678900", data_nascimento=datetime.date(1990, 1, 1))
    with pytest.raises(ValidationError):
        aluno.full_clean()


def test_mascarar_cpf():
    assert mascarar_cpf("52998224725") == "***.982.247-**"


def test_matricula_unica_por_aluno_e_turma(aluno, turma):
    Matricula.objects.create(aluno=aluno, turma=turma)
    with pytest.raises(IntegrityError):
        Matricula.objects.create(aluno=aluno, turma=turma, status=Matricula.Status.LISTA_ESPERA)


def test_frequencia_unica_por_matricula_e_aula(aluno, turma):
    matricula = Matricula.objects.create(aluno=aluno, turma=turma)
    aula = Aula.objects.create(turma=turma, data=turma.data_inicio)
    Frequencia.objects.create(matricula=matricula, aula=aula, presente=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        Frequencia.objects.create(matricula=matricula, aula=aula)


def test_certificado_gera_codigo_e_e_unico_por_matricula(aluno, turma):
    matricula = Matricula.objects.create(aluno=aluno, turma=turma)
    certificado = Certificado.objects.create(matricula=matricula)
    assert certificado.codigo_validacao is not None
    with pytest.raises(IntegrityError):
        Certificado.objects.create(matricula=matricula)


def test_admin_lista_todos_os_modelos(client, usuario_admin):
    usuario_admin.is_staff = True
    usuario_admin.save()
    client.force_login(usuario_admin)
    for url in [
        "/admin/catalogo/curso/",
        "/admin/catalogo/instrutor/",
        "/admin/turmas/turma/",
        "/admin/turmas/aula/",
        "/admin/alunos/aluno/",
        "/admin/matriculas/matricula/",
        "/admin/matriculas/frequencia/",
        "/admin/certificados/certificado/",
    ]:
        assert client.get(url).status_code == 200, url
