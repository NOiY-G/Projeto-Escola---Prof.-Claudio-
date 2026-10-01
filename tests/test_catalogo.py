from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.catalogo import services
from apps.catalogo.models import Curso, Instrutor
from apps.contas.services import PERFIL_INSTRUTOR, perfil_do_usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


# Serviços


def test_alternar_ativo(curso):
    assert services.alternar_ativo(curso).ativo is False
    curso.refresh_from_db()
    assert curso.ativo is False
    assert services.alternar_ativo(curso).ativo is True


def test_cursos_ativos(curso):
    Curso.objects.create(nome="Excel", carga_horaria=20, ativo=False)
    assert list(services.cursos_ativos()) == [curso]


def test_criar_instrutor_cria_usuario_no_grupo():
    instrutor = services.criar_instrutor(
        username="ana", email="ana@exemplo.com", senha="Senha-Forte-987", nome="Ana Lima Costa"
    )
    usuario = instrutor.usuario
    assert usuario.check_password("Senha-Forte-987")
    assert (usuario.first_name, usuario.last_name) == ("Ana", "Lima Costa")
    assert perfil_do_usuario(usuario) == PERFIL_INSTRUTOR


def test_atualizar_instrutor_sincroniza_email(instrutor):
    instrutor.nome = "Maria S."
    services.atualizar_instrutor(instrutor, email="novo@exemplo.com")
    instrutor.refresh_from_db()
    assert instrutor.nome == "Maria S."
    assert instrutor.usuario.email == "novo@exemplo.com"


# Acesso


@pytest.mark.parametrize(
    "nome_url", ["catalogo:curso_lista", "catalogo:curso_novo", "catalogo:instrutor_lista"]
)
def test_catalogo_so_para_administrador(client, usuario_instrutor, usuario_aluno, nome_url):
    url = reverse(nome_url)
    assert client.get(url).status_code == 302  # anônimo vai para o login
    for usuario in (usuario_instrutor, usuario_aluno):
        client.force_login(usuario)
        assert client.get(url).status_code == 403


# Telas de cursos


def test_listar_cursos_com_filtro(cliente_admin, curso):
    excel = Curso.objects.create(
        nome="Excel Avançado", duracao_meses=2, dias_por_semana=2, valor_mensalidade="150.00", ativo=False
    )
    excel.pre_requisitos.set([curso])
    resposta = cliente_admin.get(reverse("catalogo:curso_lista"))
    conteudo = resposta.content.decode()
    assert "Informática Básica" in conteudo and "Excel Avançado" in conteudo
    assert "R$ 150,00/mês × 2 meses" in conteudo
    assert "32 h</strong>" in conteudo and "2 dias por semana, aulas de 2 h" in conteudo
    assert "Pré-requisito: Informática Básica (ou feito em outra escola)" in conteudo
    assert "Gratuito" in conteudo

    resposta = cliente_admin.get(reverse("catalogo:curso_lista"), {"situacao": "inativos"})
    assert list(resposta.context["object_list"]) == [Curso.objects.get(nome="Excel Avançado")]


def _dados_curso(**extra):
    dados = {"nome": "Digitação", "duracao_meses": 2, "dias_por_semana": 3, "horas_por_aula": "1.5",
             "valor_mensalidade": "0", "frequencia_minima": 75, "aceita_outra_escola": "on", "ativo": "on"}
    dados.update(extra)
    return dados


def test_criar_curso_calcula_a_carga_horaria(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"), _dados_curso(pre_requisitos=[curso.pk], carga_horaria=999)
    )
    assert resposta.status_code == 302
    novo = Curso.objects.get(nome="Digitação", ativo=True)
    # 2 meses × 4 semanas × 3 dias × 1,5 h = 36 h (o que vier no formulário é ignorado)
    assert (novo.duracao_meses, novo.dias_por_semana, novo.horas_por_aula) == (2, 3, Decimal("1.5"))
    assert novo.carga_horaria == 36 and novo.gratuito and novo.aceita_outra_escola
    assert list(novo.pre_requisitos.all()) == [curso]


def test_formulario_de_curso_sem_descricao_e_com_cursos_de_pre_requisito(cliente_admin, curso):
    form = cliente_admin.get(reverse("catalogo:curso_novo")).context["form"]
    assert "descricao" not in form.fields and "carga_horaria" not in form.fields
    assert list(form.fields["pre_requisitos"].queryset) == [curso]
    # Na edição, o próprio curso não aparece como opção.
    form = cliente_admin.get(reverse("catalogo:curso_editar", args=[curso.pk])).context["form"]
    assert not form.fields["pre_requisitos"].queryset.exists()


def test_pre_requisito_nao_pode_fechar_ciclo(cliente_admin, curso):
    excel = Curso.objects.create(nome="Excel")
    excel.pre_requisitos.set([curso])  # Excel pede Informática
    resposta = cliente_admin.post(
        reverse("catalogo:curso_editar", args=[curso.pk]),
        _dados_curso(nome="Informática Básica", pre_requisitos=[excel.pk]),
    )
    assert "já depende" in resposta.context["form"].errors["pre_requisitos"][0]
    assert services.validar_pre_requisitos(curso, [curso]) == "Um curso não pode ser pré-requisito dele mesmo."


def test_criar_curso_invalido(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"),
        {"nome": "Informática Básica", "duracao_meses": 0, "dias_por_semana": 7, "horas_por_aula": "1.1",
         "valor_mensalidade": "-1", "frequencia_minima": 120},
    )
    assert resposta.status_code == 200
    erros = resposta.context["form"].errors
    assert {"nome", "duracao_meses", "dias_por_semana", "horas_por_aula", "valor_mensalidade",
            "frequencia_minima"} <= set(erros)
    assert "15 minutos" in erros["horas_por_aula"][0]


def test_editar_curso(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_editar", args=[curso.pk]),
        {"nome": "Informática Básica", "duracao_meses": 3, "dias_por_semana": 2, "horas_por_aula": "2",
         "valor_mensalidade": "99.90", "frequencia_minima": 80},
    )
    assert resposta.status_code == 302
    curso.refresh_from_db()
    assert (curso.carga_horaria, curso.duracao_meses, str(curso.valor_mensalidade), curso.frequencia_minima) == (
        48, 3, "99.90", 80,
    )
    assert curso.ativo is False and curso.aceita_outra_escola is False  # checkboxes desmarcados


def test_alternar_ativo_com_htmx(cliente_admin, curso):
    url = reverse("catalogo:curso_alternar_ativo", args=[curso.pk])
    assert cliente_admin.get(url).status_code == 405
    resposta = cliente_admin.post(url, HTTP_HX_REQUEST="true")
    assert resposta.status_code == 200
    assert "Inativo" in resposta.content.decode()
    curso.refresh_from_db()
    assert curso.ativo is False


# Telas de instrutores


def test_criar_instrutor_pela_tela(cliente_admin):
    resposta = cliente_admin.post(
        reverse("catalogo:instrutor_novo"),
        {
            "nome": "Carlos Pereira",
            "email": "carlos@exemplo.com",
            "username": "carlos",
            "senha": "Senha-Forte-987",
            "telefone": "(91) 99999-0000",
            "especialidades": "Excel",
        },
    )
    assert resposta.status_code == 302
    instrutor = Instrutor.objects.get(nome="Carlos Pereira")
    assert instrutor.usuario.username == "carlos"
    assert perfil_do_usuario(instrutor.usuario) == PERFIL_INSTRUTOR


def test_criar_instrutor_usuario_repetido_e_senha_fraca(cliente_admin, usuario_instrutor):
    total_antes = User.objects.count()
    resposta = cliente_admin.post(
        reverse("catalogo:instrutor_novo"),
        {"nome": "X", "email": "x@exemplo.com", "username": "INSTRUTOR", "senha": "123"},
    )
    assert resposta.status_code == 200
    assert {"username", "senha"} <= set(resposta.context["form"].errors)
    assert User.objects.count() == total_antes


def test_editar_instrutor(cliente_admin, instrutor):
    resposta = cliente_admin.post(
        reverse("catalogo:instrutor_editar", args=[instrutor.pk]),
        {"nome": "Maria Souza Lima", "email": "maria@exemplo.com", "telefone": "", "especialidades": ""},
    )
    assert resposta.status_code == 302
    instrutor.refresh_from_db()
    assert instrutor.nome == "Maria Souza Lima"
    assert instrutor.usuario.email == "maria@exemplo.com"


# Cálculo da carga horária


@pytest.mark.parametrize(
    "meses,dias,horas,aulas,carga",
    [
        (3, 2, "2", 24, 48),     # 3 × 4 × 2 × 2 h
        (2, 3, "1.5", 24, 36),
        (1, 1, "3", 4, 12),
        (2, 2, "1.25", 16, 20),
        (12, 6, "4", 288, 1152),
    ],
)
def test_calcular_carga_horaria(meses, dias, horas, aulas, carga):
    calculo = services.calcular(meses, dias, Decimal(horas))
    assert (calculo.semanas, calculo.aulas, calculo.carga_horaria) == (meses * 4, aulas, carga)


@pytest.mark.parametrize("meses,dias,horas", [(0, 2, "2"), (1, 0, "2"), (1, 7, "2"), (1, 2, "0")])
def test_calcular_recusa_valores_invalidos(meses, dias, horas):
    with pytest.raises(ValueError):
        services.calcular(meses, dias, Decimal(horas))


def test_previa_do_calculo_com_htmx(cliente_admin):
    url = reverse("catalogo:curso_calculo")
    conteudo = cliente_admin.get(url, {"duracao_meses": 3, "dias_por_semana": 2, "horas_por_aula": "2"}).content.decode()
    assert "Carga horária: 48 h" in conteudo and "24 aulas" in conteudo
    conteudo = cliente_admin.get(url, {"duracao_meses": 2, "dias_por_semana": 3, "horas_por_aula": "1,5"}).content.decode()
    assert "Carga horária: 36 h" in conteudo
    conteudo = cliente_admin.get(url, {"duracao_meses": "", "dias_por_semana": "9"}).content.decode()
    assert "Preencha" in conteudo


def test_formulario_de_curso_tem_a_previa(cliente_admin):
    conteudo = cliente_admin.get(reverse("catalogo:curso_novo")).content.decode()
    assert reverse("catalogo:curso_calculo") in conteudo
