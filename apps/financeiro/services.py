"""Regras do financeiro: parcelas, pagamentos (Pix e dinheiro) e comprovantes.

Regras:
- As parcelas nascem quando a matrícula fica ativa (na matrícula ou ao sair da fila).
  Valor = valor do curso − desconto; dividido em `n_parcelas` (até o máximo do curso).
  A 1ª vence no início da turma (ou hoje, se a turma já começou) e as demais a cada 30 dias.
- Cancelamento/desistência cancelam as parcelas que ainda não venceram.
- Situação: isento (nada a pagar), em dia, pendente (vencida há até N dias) ou
  inadimplente (vencida há mais de N dias). Parcela com comprovante em análise não conta
  como vencida. O sistema só avisa; não bloqueia o aluno.
"""

import datetime
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone
from PIL import Image

from apps.alunos.validators import mascarar_cpf
from apps.contas.qr import qr_code_data_uri
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO, perfil_do_usuario
from apps.matriculas.models import Matricula

from .models import Comprovante, Pagamento, Parcela

CENTAVO = Decimal("0.01")
DIAS_ENTRE_PARCELAS = 30


class FinanceiroErro(ValidationError):
    """Uma regra do financeiro impediu a operação."""


# Parcelas


def valor_total(matricula):
    """Valor do curso com o desconto da matrícula."""
    bruto = matricula.turma.curso.valor
    liquido = bruto * (Decimal("100") - matricula.desconto) / Decimal("100")
    return liquido.quantize(CENTAVO)


def dividir(total, n):
    """Divide em n parcelas; os centavos que sobram vão para a última."""
    base = (total / n).quantize(CENTAVO, rounding=ROUND_DOWN)
    return [base] * (n - 1) + [total - base * (n - 1)]


def parcelas_validas(matricula):
    return matricula.parcelas.exclude(status=Parcela.Status.CANCELADA)


@transaction.atomic
def gerar_parcelas(matricula, hoje=None):
    """Cria as parcelas da matrícula ativa. Não faz nada se já existirem ou se for isenta."""
    if parcelas_validas(matricula).exists():
        return []
    total = valor_total(matricula)
    if total <= 0:
        return []
    hoje = hoje or timezone.localdate()
    n = max(1, min(matricula.n_parcelas, matricula.turma.curso.parcelas_max))
    primeira = max(matricula.turma.data_inicio, hoje)
    # Numeração continua depois de parcelas antigas (rematrícula após cancelar).
    ultimo = matricula.parcelas.order_by("-numero").values_list("numero", flat=True).first() or 0
    return [
        Parcela.objects.create(
            matricula=matricula,
            numero=ultimo + i + 1,
            valor=valor,
            vencimento=primeira + datetime.timedelta(days=DIAS_ENTRE_PARCELAS * i),
        )
        for i, valor in enumerate(dividir(total, n))
    ]


def cancelar_parcelas_futuras(matricula, hoje=None):
    """Cancela as parcelas não pagas que ainda não venceram (desistência/cancelamento).

    Vencida é a que passou do vencimento; a que vence hoje ainda não venceu.
    """
    hoje = hoje or timezone.localdate()
    return matricula.parcelas.filter(
        status__in=[Parcela.Status.ABERTA, Parcela.Status.EM_ANALISE], vencimento__gte=hoje
    ).update(status=Parcela.Status.CANCELADA)


# Situação financeira


@dataclass(frozen=True)
class Situacao:
    codigo: str  # isento | em_dia | pendente | inadimplente
    dias_atraso: int = 0
    em_aberto: Decimal = Decimal("0")

    ROTULOS = {"isento": "Isento", "em_dia": "Em dia", "pendente": "Pendente", "inadimplente": "Inadimplente"}

    @property
    def rotulo(self):
        return self.ROTULOS[self.codigo]

    @property
    def alerta(self):
        return self.codigo in ("pendente", "inadimplente")


def situacao_das_parcelas(parcelas, hoje=None):
    """Situação a partir de uma lista de parcelas (para usar com prefetch)."""
    hoje = hoje or timezone.localdate()
    validas = [p for p in parcelas if p.status != Parcela.Status.CANCELADA]
    if not validas:
        return Situacao("isento")
    vencidas = [p for p in validas if p.status == Parcela.Status.ABERTA and p.vencimento < hoje]
    em_aberto = sum((p.valor for p in vencidas), Decimal("0"))
    if not vencidas:
        return Situacao("em_dia")
    atraso = (hoje - min(p.vencimento for p in vencidas)).days
    codigo = "inadimplente" if atraso > settings.TOLERANCIA_PAGAMENTO_DIAS else "pendente"
    return Situacao(codigo, atraso, em_aberto)


def situacao_financeira(matricula, hoje=None):
    return situacao_das_parcelas(list(matricula.parcelas.all()), hoje)


def situacoes(matriculas, hoje=None):
    """{id da matrícula: Situacao} para várias matrículas de uma vez."""
    matriculas = list(matriculas)
    por_matricula = {m.pk: [] for m in matriculas}
    for parcela in Parcela.objects.filter(matricula__in=matriculas):
        por_matricula[parcela.matricula_id].append(parcela)
    return {pk: situacao_das_parcelas(parcelas, hoje) for pk, parcelas in por_matricula.items()}


# Pagamentos


@transaction.atomic
def registrar_pagamento(
    parcela, *, forma, data, recebido_por, codigo_transacao="", observacao="", comprovante=None
):
    """Quita a parcela inteira (Pix ou dinheiro)."""
    parcela = Parcela.objects.select_for_update().get(pk=parcela.pk)
    if parcela.status not in (Parcela.Status.ABERTA, Parcela.Status.EM_ANALISE):
        raise FinanceiroErro(f"A parcela está {parcela.get_status_display().lower()} e não pode ser paga.")
    if forma not in Pagamento.Forma.values:
        raise FinanceiroErro("Forma de pagamento inválida: aceitamos só Pix ou dinheiro.")
    codigo_transacao = (codigo_transacao or "").strip() if forma == Pagamento.Forma.PIX else ""
    if data > timezone.localdate():
        raise FinanceiroErro("A data do pagamento não pode ser no futuro.")
    try:
        with transaction.atomic():
            pagamento = Pagamento.objects.create(
                parcela=parcela,
                valor=parcela.valor,
                data=data,
                forma=forma,
                codigo_transacao=codigo_transacao,
                observacao=(observacao or "").strip(),
                recebido_por=recebido_por,
                comprovante=comprovante,
            )
    except IntegrityError:
        raise FinanceiroErro("Este código de transação Pix já foi usado em outro pagamento.")
    # Outro comprovante que estivesse esperando análise perde o sentido.
    parcela.comprovantes.filter(status=Comprovante.Status.EM_ANALISE).exclude(
        pk=getattr(comprovante, "pk", None)
    ).update(status=Comprovante.Status.RECUSADO, motivo_recusa="Parcela paga por outro registro.")
    parcela.status = Parcela.Status.PAGA
    parcela.save(update_fields=["status"])
    return pagamento


@transaction.atomic
def estornar_pagamento(pagamento, *, motivo, usuario):
    """Desfaz um pagamento lançado errado. O registro fica, marcado como estornado."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise FinanceiroErro("Informe o motivo do estorno.")
    pagamento = Pagamento.objects.select_for_update().select_related("parcela").get(pk=pagamento.pk)
    if pagamento.estornado:
        raise FinanceiroErro("Este pagamento já foi estornado.")
    pagamento.estornado_em = timezone.now()
    pagamento.motivo_estorno = f"{motivo} (por {usuario.get_username()})"[:255]
    pagamento.save(update_fields=["estornado_em", "motivo_estorno"])
    if pagamento.comprovante_id:
        Comprovante.objects.filter(pk=pagamento.comprovante_id).update(
            status=Comprovante.Status.RECUSADO, motivo_recusa=f"Pagamento estornado: {motivo}"[:255]
        )
    parcela = pagamento.parcela
    parcela.status = Parcela.Status.ABERTA
    parcela.save(update_fields=["status"])
    return pagamento


# Comprovantes enviados pelo aluno

ASSINATURAS = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF-", "application/pdf"),
]


def tipo_do_arquivo(arquivo):
    """Descobre o tipo pelo conteúdo (não pela extensão). Levanta erro se não for aceito."""
    limite = settings.COMPROVANTE_TAMANHO_MAX_MB * 1024 * 1024
    if arquivo.size > limite:
        raise FinanceiroErro(f"O arquivo passa de {settings.COMPROVANTE_TAMANHO_MAX_MB} MB.")
    arquivo.seek(0)
    inicio = arquivo.read(16)
    arquivo.seek(0)
    tipo = next((t for assinatura, t in ASSINATURAS if inicio.startswith(assinatura)), None)
    if tipo is None:
        raise FinanceiroErro("Envie uma foto (JPG ou PNG) ou um PDF do comprovante.")
    if tipo.startswith("image/"):
        try:
            Image.open(arquivo).verify()
        except Exception:
            raise FinanceiroErro("A imagem enviada está corrompida.")
        finally:
            arquivo.seek(0)
    return tipo


@transaction.atomic
def enviar_comprovante(parcela, arquivo, usuario):
    parcela = Parcela.objects.select_for_update().get(pk=parcela.pk)
    if parcela.status != Parcela.Status.ABERTA:
        raise FinanceiroErro(
            f"Não é possível enviar comprovante: a parcela está {parcela.get_status_display().lower()}."
        )
    tipo = tipo_do_arquivo(arquivo)
    comprovante = Comprovante(parcela=parcela, tipo_conteudo=tipo, enviado_por=usuario)
    comprovante.arquivo.save("comprovante", arquivo, save=False)
    comprovante.save()
    parcela.status = Parcela.Status.EM_ANALISE
    parcela.save(update_fields=["status"])
    return comprovante


@transaction.atomic
def aprovar_comprovante(comprovante, *, usuario, data, codigo_transacao=""):
    comprovante = Comprovante.objects.select_for_update().get(pk=comprovante.pk)
    if comprovante.status != Comprovante.Status.EM_ANALISE:
        raise FinanceiroErro("Este comprovante já foi analisado.")
    pagamento = registrar_pagamento(
        comprovante.parcela,
        forma=Pagamento.Forma.PIX,
        data=data,
        recebido_por=usuario,
        codigo_transacao=codigo_transacao,
        observacao="Comprovante enviado pelo aluno.",
        comprovante=comprovante,
    )
    comprovante.status = Comprovante.Status.APROVADO
    comprovante.analisado_em = timezone.now()
    comprovante.analisado_por = usuario
    comprovante.save(update_fields=["status", "analisado_em", "analisado_por"])
    return pagamento


@transaction.atomic
def recusar_comprovante(comprovante, *, usuario, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise FinanceiroErro("Informe o motivo da recusa; o aluno vai ver esse texto.")
    comprovante = Comprovante.objects.select_for_update().select_related("parcela").get(pk=comprovante.pk)
    if comprovante.status != Comprovante.Status.EM_ANALISE:
        raise FinanceiroErro("Este comprovante já foi analisado.")
    comprovante.status = Comprovante.Status.RECUSADO
    comprovante.motivo_recusa = motivo[:255]
    comprovante.analisado_em = timezone.now()
    comprovante.analisado_por = usuario
    comprovante.save(update_fields=["status", "motivo_recusa", "analisado_em", "analisado_por"])
    parcela = comprovante.parcela
    if parcela.status == Parcela.Status.EM_ANALISE:
        parcela.status = Parcela.Status.ABERTA
        parcela.save(update_fields=["status"])
    return comprovante


def ultima_recusa(parcela):
    """O último comprovante recusado, se a parcela voltou a ficar aberta por causa dele."""
    if parcela.status != Parcela.Status.ABERTA:
        return None
    ultimo = parcela.comprovantes.first()
    return ultimo if ultimo and ultimo.status == Comprovante.Status.RECUSADO else None


# Permissões


def pode_ver_matricula(usuario, matricula):
    """Administrador vê tudo; aluno, só o que é dele."""
    perfil = perfil_do_usuario(usuario)
    if perfil == PERFIL_ADMINISTRADOR:
        return True
    return perfil == PERFIL_ALUNO and matricula.aluno.usuario_id == usuario.pk


# Pix "copia e cola" (BR Code estático, sem API)


def _texto_pix(texto, limite):
    """Maiúsculas, sem acentos e só caracteres aceitos pelo padrão."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    permitido = "".join(c for c in sem_acento.upper() if c.isalnum() or c in " .-")
    return permitido.strip()[:limite]


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def _crc16(dados):
    """CRC16-CCITT (polinômio 0x1021, início 0xFFFF), como pede o padrão do Pix."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def payload_pix(parcela):
    """Código Pix "copia e cola" com a chave da escola, o valor e o identificador da parcela."""
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", settings.PIX_CHAVE)
    dados = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("54", f"{parcela.valor:.2f}")
        + _campo("58", "BR")
        + _campo("59", _texto_pix(settings.PIX_NOME_RECEBEDOR, 25))
        + _campo("60", _texto_pix(settings.PIX_CIDADE, 15))
        + _campo("62", _campo("05", parcela.identificador))
        + "6304"
    )
    return dados + _crc16(dados)


# Recibo


def dados_do_recibo(pagamento):
    parcela = pagamento.parcela
    matricula = parcela.matricula
    return {
        "pagamento": pagamento,
        "parcela": parcela,
        "total_parcelas": parcelas_validas(matricula).count(),
        "aluno": matricula.aluno.nome,
        "cpf_mascarado": mascarar_cpf(matricula.aluno.cpf),
        "curso": matricula.turma.curso.nome,
        "turma": matricula.turma.codigo,
        "instituicao": settings.NOME_INSTITUICAO,
    }


def gerar_recibo_pdf(pagamento):
    from weasyprint import HTML

    html = render_to_string("financeiro/recibo_pdf.html", dados_do_recibo(pagamento))
    return HTML(string=html).write_pdf()


def resumo_do_aluno(aluno, hoje=None):
    """Para a aba Financeiro do aluno: matrículas com parcelas, pagamentos e situação."""
    matriculas = (
        aluno.matriculas.filter(parcelas__isnull=False)
        .distinct()
        .select_related("turma__curso")
        .prefetch_related("parcelas__pagamentos", "parcelas__comprovantes")
        .order_by("-data")
    )
    return [
        {"matricula": m, "situacao": situacao_das_parcelas(list(m.parcelas.all()), hoje), "parcelas": list(m.parcelas.all())}
        for m in matriculas
    ]


def parcelas_do_aluno(matricula, hoje=None):
    """Parcelas para a tela do aluno, com o Pix pronto nas que estão em aberto.

    `destacar` marca a primeira em aberto que já venceu ou vence nos próximos 7 dias.
    """
    hoje = hoje or timezone.localdate()
    parcelas = list(
        matricula.parcelas.exclude(status=Parcela.Status.CANCELADA).prefetch_related("pagamentos", "comprovantes")
    )
    for parcela in parcelas:
        parcela.recusa = ultima_recusa(parcela)
        parcela.pagamento = next((p for p in parcela.pagamentos.all() if not p.estornado), None)
        parcela.destacar = False
        if parcela.status == Parcela.Status.ABERTA:
            parcela.pix = payload_pix(parcela)
            parcela.qr = qr_code_data_uri(parcela.pix)
    urgente = next(
        (p for p in parcelas if getattr(p, "pix", None) and p.vencimento <= hoje + datetime.timedelta(days=7)),
        None,
    )
    if urgente:
        urgente.destacar = True
    return parcelas


# Lista da tela de Pagamentos

FILTROS = {
    "comprovantes": "Comprovantes para conferir",
    "vencidas": "Vencidas",
    "a_vencer": "A vencer (7 dias)",
    "pagas_mes": "Pagas no mês",
    "abertas": "Todas em aberto",
}


def parcelas_filtradas(filtro, busca="", hoje=None):
    hoje = hoje or timezone.localdate()
    qs = Parcela.objects.select_related("matricula__aluno", "matricula__turma__curso")
    abertas = [Parcela.Status.ABERTA, Parcela.Status.EM_ANALISE]
    if filtro == "comprovantes":
        qs = qs.filter(status=Parcela.Status.EM_ANALISE).order_by("vencimento")
    elif filtro == "vencidas":
        qs = qs.filter(status=Parcela.Status.ABERTA, vencimento__lt=hoje).order_by("vencimento")
    elif filtro == "a_vencer":
        qs = qs.filter(
            status__in=abertas, vencimento__gte=hoje, vencimento__lte=hoje + datetime.timedelta(days=7)
        ).order_by("vencimento")
    elif filtro == "pagas_mes":
        qs = qs.filter(
            status=Parcela.Status.PAGA,
            pagamentos__estornado_em__isnull=True,
            pagamentos__data__gte=hoje.replace(day=1),
        ).distinct().order_by("-vencimento")
    else:
        qs = qs.filter(status__in=abertas).order_by("vencimento")
    busca = (busca or "").strip()
    if busca:
        digitos = "".join(c for c in busca if c.isdigit())
        filtro_busca = Q(matricula__aluno__nome__icontains=busca)
        if digitos:
            filtro_busca |= Q(matricula__aluno__cpf__contains=digitos)
        qs = qs.filter(filtro_busca)
    return qs


def pagamento_valido(parcela):
    """O pagamento que quitou a parcela (não estornado), se houver."""
    return parcela.pagamentos.filter(estornado_em__isnull=True).first()


# Números para o painel e relatórios


def numeros_do_painel(hoje=None):
    hoje = hoje or timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    proximo_mes = (inicio_mes + datetime.timedelta(days=32)).replace(day=1)
    matriculas_com_parcela = (
        Parcela.objects.exclude(status=Parcela.Status.CANCELADA).values_list("matricula_id", flat=True).distinct()
    )
    inadimplentes = sum(
        1
        for s in situacoes(Matricula.objects.filter(pk__in=matriculas_com_parcela), hoje).values()
        if s.codigo == "inadimplente"
    )
    recebido = (
        Pagamento.objects.filter(estornado_em__isnull=True, data__gte=inicio_mes, data__lt=proximo_mes)
        .aggregate(total=Sum("valor"))["total"]
        or Decimal("0")
    )
    a_receber = (
        Parcela.objects.filter(
            status__in=[Parcela.Status.ABERTA, Parcela.Status.EM_ANALISE], vencimento__lt=proximo_mes
        ).aggregate(total=Sum("valor"))["total"]
        or Decimal("0")
    )
    return {
        "comprovantes": Comprovante.objects.filter(status=Comprovante.Status.EM_ANALISE).count(),
        "inadimplentes": inadimplentes,
        "recebido_mes": recebido,
        "a_receber_mes": a_receber,
    }
