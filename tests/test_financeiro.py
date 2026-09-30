import datetime
import io
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso
from apps.contas.services import GRUPO_ALUNO, atribuir_perfil
from apps.financeiro import services
from apps.financeiro.models import Comprovante, Pagamento, Parcela
from apps.matriculas import services as matriculas
from apps.matriculas.models import Matricula
from apps.relatorios import services as relatorios
from apps.turmas.models import Turma
from apps.turmas.services import gerar_aulas, somar_meses

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate()
D = Decimal
CPFS = ["11144477735", "39053344705", "82286187041"]


def dias(n):
    return HOJE + datetime.timedelta(days=n)


@pytest.fixture
def excel(db):
    return Curso.objects.create(nome="Excel", carga_horaria=30, duracao_meses=1, valor_mensalidade=D("150.00"))


def _turma(curso, instrutor, codigo="EXC-01", inicio=None, **extra):
    inicio = inicio or dias(10)
    dados = dict(
        curso=curso, instrutor=instrutor, codigo=codigo, data_inicio=inicio,
        data_fim=inicio + datetime.timedelta(days=70), dias_semana="seg,ter,qua,qui,sex,sab,dom",
        hora_inicio=datetime.time(18), hora_fim=datetime.time(20), vagas=10,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )
    dados.update(extra)
    return Turma.objects.create(**dados)


@pytest.fixture
def turma_paga(excel, instrutor):
    return _turma(excel, instrutor)


@pytest.fixture
def alunos(db):
    return [
        Aluno.objects.create(nome=f"Aluno {i}", cpf=cpf, data_nascimento=datetime.date(2000, 1, 1))
        for i, cpf in enumerate(CPFS, start=1)
    ]


@pytest.fixture
def aluno_logado(alunos):
    usuario = User.objects.create_user("aluno1", password="x")
    atribuir_perfil(usuario, GRUPO_ALUNO)
    alunos[0].usuario = usuario
    alunos[0].save()
    return usuario


def _matricula(turma, aluno, meses=1, **kwargs):
    """Matricula com o curso durando `meses`; as mensalidades somam sempre R$ 150,00."""
    curso = turma.curso
    if not curso.gratuito:
        curso.duracao_meses = meses
        curso.valor_mensalidade = D("150.00") / meses
        curso.save()
    return matriculas.matricular(aluno, turma, **kwargs)


def _vencer(parcela, dias_atras):
    parcela.vencimento = dias(-dias_atras)
    parcela.save(update_fields=["vencimento"])
    return parcela


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("c.png", buffer.getvalue(), content_type="image/png")


# Geração das parcelas


@pytest.mark.parametrize(
    "data,meses,esperado",
    [
        (datetime.date(2026, 1, 15), 1, datetime.date(2026, 2, 15)),
        (datetime.date(2026, 1, 31), 1, datetime.date(2026, 2, 28)),  # fevereiro não tem 31
        (datetime.date(2028, 1, 31), 1, datetime.date(2028, 2, 29)),  # ano bissexto
        (datetime.date(2026, 11, 10), 3, datetime.date(2027, 2, 10)),  # vira o ano
        (datetime.date(2026, 3, 10), -3, datetime.date(2025, 12, 10)),
    ],
)
def test_somar_meses(data, meses, esperado):
    assert somar_meses(data, meses) == esperado


def test_matricula_ativa_gera_uma_mensalidade_por_mes(turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0], meses=3)
    parcelas = list(matricula.parcelas.order_by("numero"))
    assert [p.valor for p in parcelas] == [D("50.00")] * 3
    # Vencem no mesmo dia do início da turma, nos meses seguintes.
    assert [p.vencimento for p in parcelas] == [dias(10), somar_meses(dias(10), 1), somar_meses(dias(10), 2)]
    assert all(p.status == Parcela.Status.ABERTA for p in parcelas)


def test_quem_entra_no_meio_do_curso_paga_so_os_meses_que_faltam(excel, instrutor, alunos):
    inicio = somar_meses(HOJE, -1) - datetime.timedelta(days=5)  # o 1º mês já acabou
    turma = _turma(excel, instrutor, inicio=inicio)
    matricula = _matricula(turma, alunos[0], meses=3)
    vencimentos = list(matricula.parcelas.order_by("numero").values_list("vencimento", flat=True))
    # 2º mês em curso: vence hoje; 3º no dia de sempre.
    assert vencimentos == [HOJE, somar_meses(inicio, 2)]
    assert services.vencimentos_das_mensalidades(turma) == vencimentos


def test_turma_ja_comecada_primeira_parcela_vence_hoje(excel, instrutor, alunos):
    turma = _turma(excel, instrutor, inicio=dias(-5))
    parcela = _matricula(turma, alunos[0]).parcelas.get()
    assert parcela.vencimento == HOJE


def test_desconto_e_bolsa(turma_paga, alunos):
    meia = _matricula(turma_paga, alunos[0], desconto=D("50"))
    assert meia.parcelas.get().valor == D("75.00")
    integral = _matricula(turma_paga, alunos[1], desconto=D("100"))
    assert not integral.parcelas.exists()
    assert services.situacao_financeira(integral).codigo == "isento"


def test_curso_gratuito_nao_gera_parcelas(turma, aluno):
    matricula = _matricula(turma, aluno)
    assert not matricula.parcelas.exists()


@pytest.mark.parametrize("kwargs", [{"desconto": D("101")}, {"desconto": D("-1")}])
def test_matricula_valida_desconto(turma_paga, alunos, kwargs):
    with pytest.raises(matriculas.MatriculaErro):
        _matricula(turma_paga, alunos[0], **kwargs)
    assert not Matricula.objects.exists()


def test_fila_so_gera_parcelas_ao_ser_chamada(turma_paga, alunos):
    turma_paga.vagas = 1
    turma_paga.save()
    primeira = _matricula(turma_paga, alunos[0])
    na_fila = _matricula(turma_paga, alunos[1], meses=2)
    assert na_fila.status == Matricula.Status.LISTA_ESPERA and not na_fila.parcelas.exists()
    matriculas.cancelar(primeira)
    assert [p.valor for p in na_fila.parcelas.order_by("numero")] == [D("75.00"), D("75.00")]


def test_cancelar_mantem_so_as_vencidas(turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0], meses=3)
    p1, p2, p3 = matricula.parcelas.order_by("numero")
    _vencer(p1, 20)
    p2.vencimento = HOJE  # vence hoje: ainda não venceu
    p2.save()
    matriculas.registrar_desistencia(matricula)
    status = [p.status for p in matricula.parcelas.order_by("numero")]
    assert status == [Parcela.Status.ABERTA, Parcela.Status.CANCELADA, Parcela.Status.CANCELADA]


def test_rematricula_gera_novas_parcelas_sem_colidir_numeros(turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0])
    matriculas.cancelar(matricula)
    _matricula(turma_paga, alunos[0], meses=2)
    assert list(matricula.parcelas.order_by("numero").values_list("numero", "status")) == [
        (1, "cancelada"), (2, "aberta"), (3, "aberta"),
    ]


# Situação financeira


@pytest.mark.parametrize(
    "atraso,esperado", [(None, "em_dia"), (0, "em_dia"), (1, "pendente"), (7, "pendente"), (8, "inadimplente")]
)
def test_situacao_por_dias_de_atraso(turma_paga, alunos, atraso, esperado):
    matricula = _matricula(turma_paga, alunos[0])
    if atraso is not None:
        _vencer(matricula.parcelas.get(), atraso)
    situacao = services.situacao_financeira(matricula)
    assert situacao.codigo == esperado
    if esperado != "em_dia":
        assert situacao.dias_atraso == atraso and situacao.em_aberto == D("150.00")


def test_tolerancia_configuravel(settings, turma_paga, alunos):
    settings.TOLERANCIA_PAGAMENTO_DIAS = 2
    matricula = _matricula(turma_paga, alunos[0])
    _vencer(matricula.parcelas.get(), 3)
    assert services.situacao_financeira(matricula).codigo == "inadimplente"


def test_comprovante_em_analise_nao_conta_como_atraso(turma_paga, alunos, aluno_logado):
    matricula = _matricula(turma_paga, alunos[0])
    parcela = _vencer(matricula.parcelas.get(), 30)
    services.enviar_comprovante(parcela, _png(), aluno_logado)
    assert services.situacao_financeira(matricula).codigo == "em_dia"


def test_situacoes_em_lote(turma_paga, alunos):
    em_dia = _matricula(turma_paga, alunos[0])
    atrasada = _matricula(turma_paga, alunos[1])
    _vencer(atrasada.parcelas.get(), 10)
    resultado = services.situacoes([em_dia, atrasada])
    assert {pk: s.codigo for pk, s in resultado.items()} == {em_dia.pk: "em_dia", atrasada.pk: "inadimplente"}


# Pagamentos


def _pagar(parcela, **extra):
    dados = dict(forma="pix", data=HOJE, recebido_por=None)
    dados.update(extra)
    return services.registrar_pagamento(parcela, **dados)


def test_registrar_pagamento_quita_a_parcela(turma_paga, alunos, usuario_admin):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    pagamento = _pagar(parcela, forma="dinheiro", recebido_por=usuario_admin, codigo_transacao="ignorado")
    parcela.refresh_from_db()
    assert parcela.status == Parcela.Status.PAGA
    assert (pagamento.valor, pagamento.forma, pagamento.codigo_transacao) == (D("150.00"), "dinheiro", "")
    assert pagamento.recebido_por == usuario_admin


@pytest.mark.parametrize(
    "extra,mensagem",
    [
        ({"forma": "cartao"}, "só Pix ou dinheiro"),
        ({"data": dias(1)}, "futuro"),
    ],
)
def test_registrar_pagamento_invalido(turma_paga, alunos, extra, mensagem):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    with pytest.raises(services.FinanceiroErro, match=mensagem):
        _pagar(parcela, **extra)
    assert not Pagamento.objects.exists()


def test_nao_paga_duas_vezes(turma_paga, alunos):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    _pagar(parcela)
    with pytest.raises(services.FinanceiroErro, match="paga"):
        _pagar(parcela)


def test_codigo_pix_nao_pode_repetir_mas_libera_apos_estorno(turma_paga, alunos, usuario_admin):
    p1 = _matricula(turma_paga, alunos[0]).parcelas.get()
    p2 = _matricula(turma_paga, alunos[1]).parcelas.get()
    pagamento = _pagar(p1, codigo_transacao="E123")
    with pytest.raises(services.FinanceiroErro, match="já foi usado"):
        _pagar(p2, codigo_transacao="E123")
    p2.refresh_from_db()
    assert p2.status == Parcela.Status.ABERTA
    services.estornar_pagamento(pagamento, motivo="Lançado na parcela errada", usuario=usuario_admin)
    _pagar(p2, codigo_transacao="E123")


def test_estorno(turma_paga, alunos, usuario_admin):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    pagamento = _pagar(parcela)
    with pytest.raises(services.FinanceiroErro, match="motivo"):
        services.estornar_pagamento(pagamento, motivo="  ", usuario=usuario_admin)
    services.estornar_pagamento(pagamento, motivo="Pix não caiu", usuario=usuario_admin)
    pagamento.refresh_from_db()
    parcela.refresh_from_db()
    assert pagamento.estornado and "Pix não caiu (por admin)" == pagamento.motivo_estorno
    assert parcela.status == Parcela.Status.ABERTA
    assert Pagamento.objects.count() == 1  # o registro fica
    with pytest.raises(services.FinanceiroErro, match="já foi estornado"):
        services.estornar_pagamento(pagamento, motivo="de novo", usuario=usuario_admin)


# Comprovantes


def test_enviar_e_aprovar_comprovante(turma_paga, alunos, aluno_logado, usuario_admin):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    comprovante = services.enviar_comprovante(parcela, _png(), aluno_logado)
    parcela.refresh_from_db()
    assert parcela.status == Parcela.Status.EM_ANALISE
    assert comprovante.tipo_conteudo == "image/png"
    assert comprovante.arquivo.name.startswith("comprovantes/") and "c.png" not in comprovante.arquivo.name
    with pytest.raises(services.FinanceiroErro):
        services.enviar_comprovante(parcela, _png(), aluno_logado)  # já está em análise

    pagamento = services.aprovar_comprovante(comprovante, usuario=usuario_admin, data=HOJE, codigo_transacao="E9")
    comprovante.refresh_from_db()
    parcela.refresh_from_db()
    assert (pagamento.forma, pagamento.comprovante, pagamento.codigo_transacao) == ("pix", comprovante, "E9")
    assert comprovante.status == Comprovante.Status.APROVADO and comprovante.analisado_por == usuario_admin
    assert parcela.status == Parcela.Status.PAGA
    with pytest.raises(services.FinanceiroErro, match="já foi analisado"):
        services.recusar_comprovante(comprovante, usuario=usuario_admin, motivo="x")


def test_recusar_comprovante(turma_paga, alunos, aluno_logado, usuario_admin):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    comprovante = services.enviar_comprovante(parcela, _png(), aluno_logado)
    with pytest.raises(services.FinanceiroErro, match="motivo"):
        services.recusar_comprovante(comprovante, usuario=usuario_admin, motivo="")
    services.recusar_comprovante(comprovante, usuario=usuario_admin, motivo="Valor diferente")
    parcela.refresh_from_db()
    assert parcela.status == Parcela.Status.ABERTA
    assert services.ultima_recusa(parcela).motivo_recusa == "Valor diferente"
    # Pode enviar de novo.
    services.enviar_comprovante(parcela, _png(), aluno_logado)
    parcela.refresh_from_db()
    assert services.ultima_recusa(parcela) is None


def test_pagar_na_secretaria_encerra_comprovante_pendente(turma_paga, alunos, aluno_logado):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    comprovante = services.enviar_comprovante(parcela, _png(), aluno_logado)
    _pagar(parcela, forma="dinheiro")
    comprovante.refresh_from_db()
    assert comprovante.status == Comprovante.Status.RECUSADO


@pytest.mark.parametrize(
    "conteudo,nome",
    [
        (b"%PDF-1.4 comprovante", "c.pdf"),
        (b"\xff\xd8\xff", "c.jpg"),  # cabeçalho JPEG, mas imagem quebrada
        (b"texto qualquer", "c.png"),  # extensão de imagem, conteúdo de texto
    ],
)
def test_tipos_de_arquivo(turma_paga, alunos, aluno_logado, conteudo, nome):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    arquivo = SimpleUploadedFile(nome, conteudo)
    if nome == "c.pdf":
        assert services.enviar_comprovante(parcela, arquivo, aluno_logado).tipo_conteudo == "application/pdf"
    else:
        with pytest.raises(services.FinanceiroErro):
            services.enviar_comprovante(parcela, arquivo, aluno_logado)
        assert not Comprovante.objects.exists()


def test_arquivo_grande_demais(settings, turma_paga, alunos, aluno_logado):
    settings.COMPROVANTE_TAMANHO_MAX_MB = 0
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    with pytest.raises(services.FinanceiroErro, match="MB"):
        services.enviar_comprovante(parcela, _png(), aluno_logado)


# Pix copia e cola


def test_crc16_confere_com_exemplo_do_banco_central():
    exemplo = (
        "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR"
        "5913Fulano de Tal6008BRASILIA62070503***6304"
    )
    assert services._crc16(exemplo) == "1D3D"


def test_payload_pix(settings, turma_paga, alunos):
    settings.PIX_CHAVE = "escola@exemplo.com"
    settings.PIX_NOME_RECEBEDOR = "Escola do Prof. Cláudio"
    settings.PIX_CIDADE = "Belém"
    parcela = _matricula(turma_paga, alunos[0], meses=3).parcelas.first()
    codigo = services.payload_pix(parcela)
    assert codigo.startswith("000201")
    assert "0014br.gov.bcb.pix0118escola@exemplo.com" in codigo
    assert "540550.00" in codigo  # valor da parcela
    assert "5923ESCOLA DO PROF. CLAUDIO" in codigo and "6005BELEM" in codigo
    assert f"0510{parcela.identificador}" in codigo
    corpo, crc = codigo[:-4], codigo[-4:]
    assert corpo.endswith("6304") and services._crc16(corpo) == crc


# Permissões e painel


def test_pode_ver_matricula(turma_paga, alunos, aluno_logado, usuario_admin, usuario_instrutor):
    minha = _matricula(turma_paga, alunos[0])
    outra = _matricula(turma_paga, alunos[1])
    assert services.pode_ver_matricula(usuario_admin, outra)
    assert services.pode_ver_matricula(aluno_logado, minha)
    assert not services.pode_ver_matricula(aluno_logado, outra)
    assert not services.pode_ver_matricula(usuario_instrutor, minha)


def test_numeros_do_painel(turma_paga, alunos, aluno_logado):
    m1 = _matricula(turma_paga, alunos[0])
    m2 = _matricula(turma_paga, alunos[1], meses=3)
    _vencer(m1.parcelas.get(), 20)
    _pagar(m2.parcelas.order_by("numero").first())
    services.enviar_comprovante(m2.parcelas.order_by("numero")[1], _png(), aluno_logado)
    numeros = services.numeros_do_painel()
    assert numeros["inadimplentes"] == 1
    assert numeros["comprovantes"] == 1
    assert numeros["recebido_mes"] == D("50.00")
    assert numeros["a_receber_mes"] >= D("150.00")


def test_relatorio_financeiro_por_mes(turma_paga, alunos):
    m1 = _matricula(turma_paga, alunos[0], meses=3)
    _pagar(m1.parcelas.order_by("numero").first(), forma="pix")
    m2 = _matricula(turma_paga, alunos[1])
    _pagar(m2.parcelas.get(), forma="dinheiro")
    linhas, total = relatorios.financeiro_por_mes(Turma.objects.all())
    assert (total["pix"], total["dinheiro"], total["recebido"]) == (D("50.00"), D("150.00"), D("200.00"))
    assert total["previsto"] == D("300.00") and total["em_aberto"] == D("100.00")
    csv = relatorios.gerar_csv([("mes", "Mês"), ("recebido", "Recebido")], [total])
    assert "Total;200,00" in csv


# Telas


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


def test_tela_de_pagamentos(cliente_admin, turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0])
    _vencer(matricula.parcelas.get(), 10)
    conteudo = cliente_admin.get(reverse("financeiro:pagamentos"), {"ver": "vencidas"}).content.decode()
    assert "Aluno 1" in conteudo and "R$ 150,00" in conteudo and "Inadimplente" in conteudo
    assert "Registrar pagamento" in conteudo


def test_pagamentos_so_para_administrador(client, usuario_instrutor, aluno_logado):
    for usuario in (usuario_instrutor, aluno_logado):
        client.force_login(usuario)
        assert client.get(reverse("financeiro:pagamentos")).status_code == 403


def test_registrar_pela_tela(cliente_admin, turma_paga, alunos, usuario_admin):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    url = reverse("financeiro:registrar", args=[parcela.pk])
    resposta = cliente_admin.post(url, {"forma": "dinheiro", "data": HOJE.isoformat()}, follow=True)
    assert "Pagamento de R$ 150,00 (Dinheiro) registrado" in resposta.content.decode()
    assert Pagamento.objects.get().recebido_por == usuario_admin


def test_aluno_ve_pix_e_envia_comprovante(client, turma_paga, alunos, aluno_logado):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    client.force_login(aluno_logado)
    tela = client.get(reverse("matriculas:minhas_matriculas")).content.decode()
    assert "Pagar com Pix" in tela and "data:image/png;base64," in tela
    assert services.payload_pix(parcela) in tela
    resposta = client.post(
        reverse("financeiro:enviar_comprovante", args=[parcela.pk]), {"arquivo": _png()}, follow=True
    )
    assert "Comprovante enviado" in resposta.content.decode()
    parcela.refresh_from_db()
    assert parcela.status == Parcela.Status.EM_ANALISE


def test_aluno_nao_envia_comprovante_de_outro(client, turma_paga, alunos, aluno_logado):
    parcela_alheia = _matricula(turma_paga, alunos[1]).parcelas.get()
    client.force_login(aluno_logado)
    resposta = client.post(reverse("financeiro:enviar_comprovante", args=[parcela_alheia.pk]), {"arquivo": _png()})
    assert resposta.status_code == 404
    assert not Comprovante.objects.exists()


def test_arquivo_do_comprovante_e_protegido(client, turma_paga, alunos, aluno_logado, usuario_admin, usuario_instrutor):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    comprovante = services.enviar_comprovante(parcela, _png(), aluno_logado)
    url = reverse("financeiro:arquivo_comprovante", args=[comprovante.pk])
    assert client.get(url).status_code == 302  # login
    for usuario, status in [(usuario_admin, 200), (aluno_logado, 200), (usuario_instrutor, 404)]:
        client.force_login(usuario)
        resposta = client.get(url)
        assert resposta.status_code == status
        if status == 200:
            assert resposta["Content-Type"] == "image/png"
            assert resposta["Cache-Control"] == "private, no-store"
    outro = User.objects.create_user("aluno2", password="x")
    atribuir_perfil(outro, GRUPO_ALUNO)
    alunos[1].usuario = outro
    alunos[1].save()
    client.force_login(outro)
    assert client.get(url).status_code == 404


def test_conferir_pela_tela(cliente_admin, turma_paga, alunos, aluno_logado):
    p1, p2 = _matricula(turma_paga, alunos[0], meses=2).parcelas.order_by("numero")
    c1 = services.enviar_comprovante(p1, _png(), aluno_logado)
    c2 = services.enviar_comprovante(p2, _png(), aluno_logado)
    url = reverse("financeiro:conferir", args=[c1.pk])
    assert "Identificador no Pix" in cliente_admin.get(url).content.decode()
    cliente_admin.post(url, {"acao": "aprovar", "data": HOJE.isoformat(), "codigo_transacao": "E1"})
    cliente_admin.post(reverse("financeiro:conferir", args=[c2.pk]), {"acao": "recusar", "motivo": "Ilegível"})
    p1.refresh_from_db()
    p2.refresh_from_db()
    assert (p1.status, p2.status) == (Parcela.Status.PAGA, Parcela.Status.ABERTA)
    tela = cliente_admin.get(reverse("financeiro:conferir", args=[c2.pk])).content.decode()
    assert "já foi recusado" in tela


def test_estornar_pela_tela(cliente_admin, turma_paga, alunos):
    parcela = _matricula(turma_paga, alunos[0]).parcelas.get()
    pagamento = _pagar(parcela)
    url = reverse("financeiro:estornar", args=[pagamento.pk])
    assert cliente_admin.get(url).status_code == 405
    resposta = cliente_admin.post(url, {"motivo": "Duplicado"}, follow=True)
    assert "Pagamento estornado" in resposta.content.decode()
    assert "Estornado em" in resposta.content.decode()  # voltou à ficha do aluno


def test_recibo(client, turma_paga, alunos, aluno_logado, usuario_admin):
    pagamento = _pagar(_matricula(turma_paga, alunos[0]).parcelas.get(), forma="dinheiro")
    dados = services.dados_do_recibo(pagamento)
    assert dados["aluno"] == "Aluno 1" and dados["cpf_mascarado"] == "***.444.777-**"
    url = reverse("financeiro:recibo", args=[pagamento.pk])
    client.force_login(aluno_logado)
    resposta = client.get(url)
    assert resposta.status_code == 200 and resposta.content.startswith(b"%PDF")
    services.estornar_pagamento(pagamento, motivo="erro", usuario=usuario_admin)
    assert client.get(url).status_code == 404


def test_chamada_avisa_sem_mostrar_valores(client, usuario_instrutor, excel, instrutor, alunos):
    turma = _turma(excel, instrutor, inicio=dias(-3))
    gerar_aulas(turma)
    matricula = _matricula(turma, alunos[0])
    _vencer(matricula.parcelas.get(), 15)
    client.force_login(usuario_instrutor)
    aula = turma.aulas.get(data=HOJE)
    conteudo = client.get(reverse("matriculas:chamada", args=[turma.pk, aula.pk])).content.decode()
    assert "Pagamento pendente – procure a secretaria" in conteudo
    assert "R$" not in conteudo


def test_ficha_do_aluno_mostra_financeiro(cliente_admin, turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0], meses=3, desconto=D("10"))
    _pagar(matricula.parcelas.order_by("numero").first())
    conteudo = cliente_admin.get(reverse("alunos:aluno_detalhe", args=[alunos[0].pk])).content.decode()
    assert "Financeiro" in conteudo and "com 10% de desconto" in conteudo
    assert "R$ 45,00" in conteudo and "Recibo (PDF)" in conteudo and "Estornar" in conteudo


def test_nova_matricula_com_mensalidades_pela_tela(cliente_admin, turma_paga, alunos):
    turma_paga.curso.duracao_meses = 2
    turma_paga.curso.valor_mensalidade = D("75.00")
    turma_paga.curso.save()
    form = cliente_admin.get(reverse("matriculas:matricula_nova")).context["form"]
    assert "R$ 75,00/mês × 2" in str(form["turma"])
    assert "n_parcelas" not in form.fields
    cliente_admin.post(
        reverse("matriculas:matricula_nova"),
        {"aluno": alunos[0].pk, "turma": turma_paga.pk, "desconto": "20"},
    )
    matricula = Matricula.objects.get()
    assert matricula.desconto == D("20")
    assert list(matricula.parcelas.values_list("valor", flat=True)) == [D("60.00"), D("60.00")]


def test_painel_mostra_financeiro(cliente_admin):
    conteudo = cliente_admin.get(reverse("contas:painel")).content.decode()
    assert "Comprovantes para conferir" in conteudo and "Inadimplentes" in conteudo
    assert "vencido há mais de 7 dias" in conteudo


def test_relatorio_financeiro_na_tela(cliente_admin, turma_paga, alunos):
    _pagar(_matricula(turma_paga, alunos[0]).parcelas.get())
    conteudo = cliente_admin.get(reverse("relatorios:relatorio", args=["financeiro"])).content.decode()
    assert "R$ 150,00" in conteudo


def test_so_destaca_o_pix_vencido_ou_proximo(turma_paga, alunos):
    matricula = _matricula(turma_paga, alunos[0], meses=3)  # vencem em 10 dias, 1 e 2 meses depois
    assert not any(p.destacar for p in services.parcelas_do_aluno(matricula))
    _vencer(matricula.parcelas.order_by("numero")[1], 3)
    destaques = [p.numero for p in services.parcelas_do_aluno(matricula) if p.destacar]
    assert destaques == [2]
