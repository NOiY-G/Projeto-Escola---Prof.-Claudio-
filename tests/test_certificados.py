import base64
import datetime
import io

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.alunos.models import Aluno
from apps.certificados import services
from apps.certificados.models import Certificado
from apps.contas.services import GRUPO_ALUNO, atribuir_perfil
from apps.matriculas import services as matriculas
from apps.matriculas.models import Matricula
from apps.turmas import services as turmas
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate()
Status = Matricula.Status
CPFS = ["11144477735", "39053344705", "82286187041", "71428793860"]


@pytest.fixture
def turma_andando(curso, instrutor):
    """4 aulas já realizadas (de -3 até hoje) e 3 futuras; frequência mínima 75%."""
    turma = Turma.objects.create(
        curso=curso, instrutor=instrutor, codigo="INF-2026-05",
        data_inicio=HOJE - datetime.timedelta(days=3), data_fim=HOJE + datetime.timedelta(days=3),
        dias_semana="seg,ter,qua,qui,sex,sab,dom",
        hora_inicio=datetime.time(8), hora_fim=datetime.time(10), vagas=3,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )
    turmas.gerar_aulas(turma)
    return turma


@pytest.fixture
def alunos(db):
    return [
        Aluno.objects.create(nome=f"Aluno {i}", cpf=cpf, data_nascimento=datetime.date(2000, 1, 1))
        for i, cpf in enumerate(CPFS, start=1)
    ]


@pytest.fixture
def turma_com_chamadas(turma_andando, alunos):
    """Aluno 1: 4/4 (100%). Aluno 2: 3/4 (75%, no limite). Aluno 3: 2/4 (50%). Aluno 4: na fila."""
    m1, m2, m3, m4 = (matriculas.matricular(a, turma_andando) for a in alunos)
    assert m4.status == Status.LISTA_ESPERA
    presencas = {-3: [m1, m2, m3], -2: [m1, m2, m3], -1: [m1, m2], 0: [m1]}
    for dias, presentes in presencas.items():
        aula = turma_andando.aulas.get(data=HOJE + datetime.timedelta(days=dias))
        matriculas.registrar_chamada(aula, presentes=[m.pk for m in presentes])
    return turma_andando, (m1, m2, m3, m4)


def _status(matricula):
    matricula.refresh_from_db()
    return matricula.status


# Regra 5: conclusão da turma


def test_previa_da_conclusao(turma_com_chamadas):
    turma, (m1, m2, m3, _) = turma_com_chamadas
    previa = {linha.matricula: (linha.percentual, linha.aprovado) for linha in services.previa_conclusao(turma)}
    assert previa == {m1: (100.0, True), m2: (75.0, True), m3: (50.0, False)}


def test_concluir_turma(turma_com_chamadas):
    turma, (m1, m2, m3, m4) = turma_com_chamadas
    resultado = services.concluir_turma(turma)

    assert resultado.concluidas == [m1, m2]
    assert resultado.desistentes == [m3]
    assert resultado.espera_canceladas == [m4]
    assert [_status(m) for m in (m1, m2, m3, m4)] == [
        Status.CONCLUIDA, Status.CONCLUIDA, Status.DESISTENTE, Status.CANCELADA,
    ]
    # Só quem concluiu ganha certificado.
    assert set(Certificado.objects.values_list("matricula_id", flat=True)) == {m1.pk, m2.pk}
    turma.refresh_from_db()
    assert turma.status == Turma.Status.CONCLUIDA


def test_frequencia_minima_do_curso_e_respeitada(turma_com_chamadas):
    turma, (m1, m2, _, _) = turma_com_chamadas
    turma.curso.frequencia_minima = 80
    turma.curso.save()
    services.concluir_turma(turma)
    assert _status(m1) == Status.CONCLUIDA
    assert _status(m2) == Status.DESISTENTE  # 75% < 80%


@pytest.mark.parametrize(
    "status", [Turma.Status.PLANEJADA, Turma.Status.CONCLUIDA, Turma.Status.CANCELADA]
)
def test_so_conclui_turma_aberta_ou_em_andamento(turma_com_chamadas, status):
    turma, (m1, *_) = turma_com_chamadas
    turma.status = status
    turma.save()
    with pytest.raises(services.CertificadoErro):
        services.concluir_turma(turma)
    assert _status(m1) == Status.ATIVA
    assert not Certificado.objects.exists()


def test_nao_conclui_turma_sem_aulas_realizadas(turma, aluno):
    turmas.gerar_aulas(turma)
    matriculas.matricular(aluno, turma)
    with pytest.raises(services.CertificadoErro, match="nenhuma aula"):
        services.concluir_turma(turma, hoje=datetime.date(2026, 10, 1))


def test_chamada_bloqueada_depois_de_concluir(turma_com_chamadas):
    turma, (m1, *_) = turma_com_chamadas
    services.concluir_turma(turma)
    with pytest.raises(matriculas.MatriculaErro):
        matriculas.registrar_chamada(turma.aulas.first(), presentes=[])


# Emissão


def test_emitir_certificado_e_idempotente(turma_com_chamadas):
    turma, (m1, *_) = turma_com_chamadas
    services.concluir_turma(turma)
    m1.refresh_from_db()
    assert services.emitir_certificado(m1) == services.emitir_certificado(m1) == m1.certificado


def test_so_matricula_concluida_recebe_certificado(turma_com_chamadas):
    _, (m1, *_) = turma_com_chamadas
    with pytest.raises(services.CertificadoErro):
        services.emitir_certificado(m1)


def test_concluidas_sem_certificado(turma_com_chamadas):
    turma, (m1, m2, *_) = turma_com_chamadas
    services.concluir_turma(turma)
    m1.certificado.delete()
    assert list(services.concluidas_sem_certificado()) == [m1]


# Regra 6: conteúdo do certificado


@pytest.fixture
def certificado(turma_com_chamadas):
    turma, (m1, *_) = turma_com_chamadas
    services.concluir_turma(turma)
    return Certificado.objects.get(matricula=m1)


def test_html_do_certificado_tem_os_dados_da_regra_6(certificado, settings):
    settings.NOME_INSTITUICAO = "Escola Exemplo"
    url = f"https://exemplo.com/certificados/validar/{certificado.codigo_validacao}/"
    html = services.html_do_certificado(certificado, url)
    turma = certificado.matricula.turma
    for trecho in [
        "Escola Exemplo",
        "Aluno 1",
        "***.444.777-**",  # CPF 111.444.777-35 mascarado
        "Informática Básica",
        "40 horas",
        f"{turma.data_inicio:%d/%m/%Y} a {turma.data_fim:%d/%m/%Y}",
        url,
        "data:image/png;base64,",
    ]:
        assert trecho in html, trecho
    assert "11144477735" not in html and "111.444.777-35" not in html


def test_qr_code_e_uma_imagem_png():
    uri = services.qr_code_data_uri("https://exemplo.com/x/")
    imagem = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert imagem.format == "PNG"
    assert imagem.size[0] == imagem.size[1] > 100


def test_gerar_pdf(certificado):
    pdf = services.gerar_pdf(certificado, "https://exemplo.com/v/")
    assert pdf.startswith(b"%PDF")


# Download


def test_admin_baixa_pdf_com_qr_para_a_validacao(client, usuario_admin, certificado, monkeypatch):
    urls = []
    monkeypatch.setattr(services, "gerar_pdf", lambda cert, url: urls.append(url) or b"%PDF-teste")
    client.force_login(usuario_admin)
    resposta = client.get(reverse("certificados:pdf", args=[certificado.codigo_validacao]))
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/pdf"
    assert "attachment" in resposta["Content-Disposition"]
    assert urls == [f"http://testserver/certificados/validar/{certificado.codigo_validacao}/"]


def test_aluno_baixa_so_o_proprio_certificado(client, certificado, alunos):
    dono = User.objects.create_user("dono", password="x")
    outro = User.objects.create_user("outro", password="x")
    for usuario, aluno in [(dono, alunos[0]), (outro, alunos[1])]:
        atribuir_perfil(usuario, GRUPO_ALUNO)
        aluno.usuario = usuario
        aluno.save()
    url = reverse("certificados:pdf", args=[certificado.codigo_validacao])

    client.force_login(dono)
    assert client.get(url).status_code == 200
    minhas = client.get(reverse("matriculas:minhas_matriculas")).content.decode()
    assert "Baixar certificado" in minhas

    client.force_login(outro)
    assert client.get(url).status_code == 404


def test_instrutor_e_anonimo_nao_baixam(client, certificado, usuario_instrutor):
    url = reverse("certificados:pdf", args=[certificado.codigo_validacao])
    assert client.get(url).status_code == 302  # login
    client.force_login(usuario_instrutor)
    assert client.get(url).status_code == 404


# Regra 7: validação pública


def test_validacao_publica_de_certificado_valido(client, certificado):
    resposta = client.get(reverse("certificados:validar", args=[certificado.codigo_validacao]))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Certificado válido" in conteudo
    assert "Aluno 1" in conteudo and "Informática Básica" in conteudo and "40 h" in conteudo
    assert "***.444.777-**" in conteudo
    assert "11144477735" not in conteudo
    # Não mostra frequência, turma nem dados de contato.
    assert "%" not in conteudo.split("Certificado válido")[1]


@pytest.mark.parametrize("codigo", ["00000000-0000-0000-0000-000000000000", "nao-e-um-codigo"])
def test_validacao_de_codigo_inexistente_ou_invalido(client, codigo):
    resposta = client.get(reverse("certificados:validar", args=[codigo]))
    assert resposta.status_code == 404
    assert "Certificado não encontrado" in resposta.content.decode()


def test_formulario_de_validacao(client, certificado):
    assert "Digite o código" in client.get(reverse("certificados:validar_busca")).content.decode()
    resposta = client.get(
        reverse("certificados:validar_busca"), {"codigo": f"  {certificado.codigo_validacao} "}
    )
    assert resposta.url == reverse("certificados:validar", args=[str(certificado.codigo_validacao)])


# Telas do administrador


def test_tela_de_conclusao_mostra_previa_e_conclui(client, usuario_admin, turma_com_chamadas):
    turma, (m1, m2, m3, _) = turma_com_chamadas
    client.force_login(usuario_admin)
    url = reverse("certificados:concluir_turma", args=[turma.pk])
    previa = client.get(url).content.decode()
    assert "Conclui" in previa and "Desistente" in previa and "50%" in previa
    assert "lista de espera serão canceladas" in previa

    resposta = client.post(url, follow=True)
    conteudo = resposta.content.decode()
    assert "2 aluno(s) concluíram" in conteudo and "1 ficaram como desistentes" in conteudo
    assert "Certificado (PDF)" in conteudo
    assert "Concluir turma</a>" not in conteudo


def test_tela_de_conclusao_explica_quando_nao_pode(client, usuario_admin, turma):
    client.force_login(usuario_admin)
    turma.status = Turma.Status.PLANEJADA
    turma.save()
    conteudo = client.get(reverse("certificados:concluir_turma", args=[turma.pk])).content.decode()
    assert "não pode ser concluída" in conteudo
    assert "Concluir turma e emitir" not in conteudo


def test_conclusao_so_para_administrador(client, usuario_instrutor, turma_com_chamadas):
    turma, (m1, *_) = turma_com_chamadas
    client.force_login(usuario_instrutor)
    assert client.post(reverse("certificados:concluir_turma", args=[turma.pk])).status_code == 403
    assert _status(m1) == Status.ATIVA


def test_lista_e_emissao_manual(client, usuario_admin, turma_com_chamadas):
    turma, (m1, *_) = turma_com_chamadas
    services.concluir_turma(turma)
    m1.certificado.delete()
    client.force_login(usuario_admin)
    lista = client.get(reverse("certificados:lista")).content.decode()
    assert "Concluídos sem certificado" in lista
    client.post(reverse("certificados:emitir", args=[m1.pk]))
    assert Certificado.objects.filter(matricula=m1).exists()


def test_chamada_de_turma_concluida_fica_so_leitura(client, usuario_admin, turma_com_chamadas):
    turma, (m1, m2, m3, _) = turma_com_chamadas
    services.concluir_turma(turma)
    client.force_login(usuario_admin)
    detalhe = client.get(reverse("turmas:turma_detalhe", args=[turma.pk])).content.decode()
    assert "Ver chamadas" in detalhe and "Fazer chamada" not in detalhe

    aula = turma.aulas.get(data=HOJE)
    tela = client.get(reverse("matriculas:chamada", args=[turma.pk, aula.pk])).content.decode()
    assert "só leitura" in tela and "Salvar chamada" not in tela
    # Mostra o registro de quem estava na turma, mesmo sem matrículas ativas.
    assert "Aluno 1" in tela and "Aluno 3" in tela
