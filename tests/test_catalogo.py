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
    Curso.objects.create(nome="Excel Avançado", carga_horaria=20, valor="150.00", ativo=False)
    resposta = cliente_admin.get(reverse("catalogo:curso_lista"))
    conteudo = resposta.content.decode()
    assert "Informática Básica" in conteudo and "Excel Avançado" in conteudo
    assert "R$ 150,00" in conteudo
    assert "Gratuito" in conteudo

    resposta = cliente_admin.get(reverse("catalogo:curso_lista"), {"situacao": "inativos"})
    assert list(resposta.context["object_list"]) == [Curso.objects.get(nome="Excel Avançado")]


def test_criar_curso(cliente_admin):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"),
        {"nome": "Digitação", "carga_horaria": 20, "valor": "0", "frequencia_minima": 75,
         "parcelas_max": 1, "ativo": "on"},
    )
    assert resposta.status_code == 302
    assert Curso.objects.filter(nome="Digitação", ativo=True).exists()


def test_criar_curso_invalido(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"),
        {"nome": "Informática Básica", "carga_horaria": 0, "valor": "-1", "frequencia_minima": 120},
    )
    assert resposta.status_code == 200
    erros = resposta.context["form"].errors
    assert {"nome", "carga_horaria", "valor", "frequencia_minima"} <= set(erros)


def test_editar_curso(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_editar", args=[curso.pk]),
        {"nome": "Informática Básica", "carga_horaria": 60, "valor": "99.90", "frequencia_minima": 80,
         "parcelas_max": 3},
    )
    assert resposta.status_code == 302
    curso.refresh_from_db()
    assert (curso.carga_horaria, str(curso.valor), curso.frequencia_minima) == (60, "99.90", 80)
    assert curso.ativo is False  # checkbox desmarcado


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
