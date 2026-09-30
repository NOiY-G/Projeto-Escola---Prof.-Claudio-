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
    Curso.objects.create(
        nome="Excel Avançado", carga_horaria=20, duracao_meses=2, valor_mensalidade="150.00", ativo=False
    )
    resposta = cliente_admin.get(reverse("catalogo:curso_lista"))
    conteudo = resposta.content.decode()
    assert "Informática Básica" in conteudo and "Excel Avançado" in conteudo
    assert "R$ 150,00/mês × 2 meses" in conteudo
    assert "mínimo 2 dias por semana" in conteudo  # Excel Avançado: 10 aulas de 2 h em 8 semanas
    assert "Gratuito" in conteudo

    resposta = cliente_admin.get(reverse("catalogo:curso_lista"), {"situacao": "inativos"})
    assert list(resposta.context["object_list"]) == [Curso.objects.get(nome="Excel Avançado")]


def test_criar_curso(cliente_admin):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"),
        {"nome": "Digitação", "carga_horaria": 20, "duracao_meses": 2, "horas_por_aula": "1.5",
         "valor_mensalidade": "0", "frequencia_minima": 75, "ativo": "on"},
    )
    assert resposta.status_code == 302
    curso = Curso.objects.get(nome="Digitação", ativo=True)
    assert (curso.duracao_meses, curso.horas_por_aula, curso.gratuito) == (2, Decimal("1.5"), True)


def test_criar_curso_invalido(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_novo"),
        {"nome": "Informática Básica", "carga_horaria": 0, "duracao_meses": 0, "horas_por_aula": "0",
         "valor_mensalidade": "-1", "frequencia_minima": 120},
    )
    assert resposta.status_code == 200
    erros = resposta.context["form"].errors
    assert {"nome", "carga_horaria", "duracao_meses", "horas_por_aula", "valor_mensalidade",
            "frequencia_minima"} <= set(erros)


def test_curso_recusa_carga_que_nao_cabe_no_periodo(cliente_admin):
    # 1 mês = 4 semanas × 6 dias (segunda a sábado) × 2 h = 48 h no máximo.
    dados = {"nome": "Intensivo", "duracao_meses": 1, "horas_por_aula": "2", "valor_mensalidade": "0",
             "frequencia_minima": 75}
    resposta = cliente_admin.post(reverse("catalogo:curso_novo"), {**dados, "carga_horaria": 49})
    assert "Não cabe" in resposta.context["form"].errors["carga_horaria"][0]
    resposta = cliente_admin.post(reverse("catalogo:curso_novo"), {**dados, "carga_horaria": 48})
    assert resposta.status_code == 302


def test_editar_curso(cliente_admin, curso):
    resposta = cliente_admin.post(
        reverse("catalogo:curso_editar", args=[curso.pk]),
        {"nome": "Informática Básica", "carga_horaria": 60, "duracao_meses": 3, "horas_por_aula": "2",
         "valor_mensalidade": "99.90", "frequencia_minima": 80},
    )
    assert resposta.status_code == 302
    curso.refresh_from_db()
    assert (curso.carga_horaria, curso.duracao_meses, str(curso.valor_mensalidade), curso.frequencia_minima) == (
        60, 3, "99.90", 80,
    )
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


# Cálculo da carga horária


@pytest.mark.parametrize(
    "carga,meses,horas,aulas,dias_minimos",
    [
        (40, 2, "2", 20, 3),    # 20 aulas em 8 semanas: 2,5 → 3 dias
        (40, 3, "2", 20, 2),    # 20 aulas em 12 semanas: 1,67 → 2 dias
        (20, 3, "2", 10, 1),
        (30, 2, "1.5", 20, 3),  # 30 ÷ 1,5 = 20 aulas
        (25, 1, "2", 13, 4),    # 12,5 aulas → 13
        (48, 1, "2", 24, 6),    # segunda a sábado, todas as semanas
        (49, 1, "2", 25, 7),    # não cabe
    ],
)
def test_planejar_dias_minimos(carga, meses, horas, aulas, dias_minimos):
    plano = services.planejar(carga, meses, Decimal(horas))
    assert (plano.aulas_necessarias, plano.dias_minimos) == (aulas, dias_minimos)
    assert plano.semanas == meses * 4
    assert plano.cabe == (dias_minimos <= 6)
    assert plano.carga_maxima == 6 * meses * 4 * Decimal(horas)


def test_curso_mostra_dias_minimos(curso):
    curso.duracao_meses, curso.horas_por_aula = 2, Decimal("2")
    assert curso.dias_minimos == 3


def test_previa_do_planejamento_com_htmx(cliente_admin):
    url = reverse("catalogo:curso_planejamento")
    conteudo = cliente_admin.get(url, {"carga_horaria": 40, "duracao_meses": 2, "horas_por_aula": "2"}).content.decode()
    assert "Mínimo de 3 dias de aula por semana" in conteudo and "20 aulas" in conteudo
    conteudo = cliente_admin.get(url, {"carga_horaria": 100, "duracao_meses": 1, "horas_por_aula": "2"}).content.decode()
    assert "Não cabe" in conteudo
    conteudo = cliente_admin.get(url, {"carga_horaria": "", "duracao_meses": "x"}).content.decode()
    assert "Preencha" in conteudo


def test_formulario_de_curso_tem_a_previa(cliente_admin):
    conteudo = cliente_admin.get(reverse("catalogo:curso_novo")).content.decode()
    assert reverse("catalogo:curso_planejamento") in conteudo
