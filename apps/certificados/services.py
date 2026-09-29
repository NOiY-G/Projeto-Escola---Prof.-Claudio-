import base64
import io
import uuid
from dataclasses import dataclass, field

import qrcode
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.alunos.validators import mascarar_cpf
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO, perfil_do_usuario
from apps.matriculas import services as matriculas_services
from apps.matriculas.models import Matricula
from apps.turmas.models import Turma

from .models import Certificado

STATUS_TURMA_PODE_CONCLUIR = (Turma.Status.INSCRICOES_ABERTAS, Turma.Status.EM_ANDAMENTO)


class CertificadoErro(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# Conclusão da turma (regra 5)


@dataclass
class LinhaPrevia:
    matricula: Matricula
    percentual: float
    aprovado: bool


def previa_conclusao(turma, hoje=None):
    """O que acontece com cada matrícula ativa se a turma for concluída agora."""
    minimo = turma.curso.frequencia_minima
    linhas = []
    for matricula in matriculas_services.matriculas_da_chamada(turma):
        percentual = matriculas_services.percentual_frequencia(matricula, hoje) or 0.0
        linhas.append(LinhaPrevia(matricula, percentual, percentual >= minimo))
    return linhas


@dataclass
class ResultadoConclusao:
    concluidas: list = field(default_factory=list)
    desistentes: list = field(default_factory=list)
    espera_canceladas: list = field(default_factory=list)


def verificar_conclusao(turma, hoje=None):
    """Levanta CertificadoErro se a turma ainda não pode ser concluída."""
    if turma.status not in STATUS_TURMA_PODE_CONCLUIR:
        raise CertificadoErro(
            f"A turma {turma.codigo} está {turma.get_status_display().lower()} e não pode ser concluída."
        )
    if not matriculas_services.aulas_realizadas(turma, hoje).exists():
        raise CertificadoErro(
            "A turma ainda não teve nenhuma aula; não há frequência para concluir."
        )


@transaction.atomic
def concluir_turma(turma, hoje=None) -> ResultadoConclusao:
    """Regra 5: ativas com frequência ≥ mínima do curso viram `concluida` e
    ganham certificado; as demais viram `desistente`. Quem ainda estava na
    lista de espera tem a matrícula cancelada. A turma passa a `concluida`.
    """
    turma = Turma.objects.select_for_update().select_related("curso").get(pk=turma.pk)
    verificar_conclusao(turma, hoje)

    resultado = ResultadoConclusao()
    for linha in previa_conclusao(turma, hoje):
        matricula = linha.matricula
        if linha.aprovado:
            matricula.status = Matricula.Status.CONCLUIDA
            matricula.save(update_fields=["status"])
            Certificado.objects.get_or_create(matricula=matricula)
            resultado.concluidas.append(matricula)
        else:
            matricula.status = Matricula.Status.DESISTENTE
            matricula.save(update_fields=["status"])
            resultado.desistentes.append(matricula)

    for matricula in matriculas_services.lista_espera(turma):
        matricula.status = Matricula.Status.CANCELADA
        matricula.save(update_fields=["status"])
        resultado.espera_canceladas.append(matricula)

    turma.status = Turma.Status.CONCLUIDA
    turma.save(update_fields=["status"])
    return resultado


# Certificados


def emitir_certificado(matricula) -> Certificado:
    """Emite (ou devolve o já emitido) o certificado de uma matrícula concluída."""
    if matricula.status != Matricula.Status.CONCLUIDA:
        raise CertificadoErro("Só matrículas concluídas recebem certificado.")
    certificado, _ = Certificado.objects.get_or_create(matricula=matricula)
    return certificado


def concluidas_sem_certificado():
    return (
        Matricula.objects.filter(status=Matricula.Status.CONCLUIDA, certificado__isnull=True)
        .select_related("aluno", "turma__curso")
        .order_by("turma__codigo", "aluno__nome")
    )


def buscar_por_codigo(codigo):
    """Certificado pelo código de validação, ou None (código inválido ou inexistente)."""
    try:
        codigo = uuid.UUID(str(codigo).strip())
    except ValueError:
        return None
    return (
        Certificado.objects.select_related("matricula__aluno", "matricula__turma__curso")
        .filter(codigo_validacao=codigo)
        .first()
    )


def pode_baixar(usuario, certificado):
    """Administrador baixa qualquer certificado; aluno, só os próprios."""
    perfil = perfil_do_usuario(usuario)
    if perfil == PERFIL_ADMINISTRADOR:
        return True
    return perfil == PERFIL_ALUNO and certificado.matricula.aluno.usuario_id == usuario.pk


def dados_do_certificado(certificado):
    """Tudo que o certificado e a página de validação mostram (regra 6)."""
    matricula = certificado.matricula
    turma = matricula.turma
    return {
        "nome": matricula.aluno.nome,
        "cpf_mascarado": mascarar_cpf(matricula.aluno.cpf),
        "curso": turma.curso.nome,
        "carga_horaria": turma.curso.carga_horaria,
        "data_inicio": turma.data_inicio,
        "data_fim": turma.data_fim,
        "turma": turma.codigo,
        "emitido_em": timezone.localtime(certificado.emitido_em),
        "codigo": certificado.codigo_validacao,
    }


def qr_code_data_uri(texto):
    imagem = qrcode.make(texto, box_size=10, border=1)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def html_do_certificado(certificado, url_validacao) -> str:
    return render_to_string(
        "certificados/certificado_pdf.html",
        {
            **dados_do_certificado(certificado),
            "instituicao": settings.NOME_INSTITUICAO,
            "url_validacao": url_validacao,
            "qr_code": qr_code_data_uri(url_validacao),
        },
    )


def gerar_pdf(certificado, url_validacao) -> bytes:
    """Regra 6: PDF do certificado com QR Code apontando para a página de validação."""
    from weasyprint import HTML

    return HTML(string=html_do_certificado(certificado, url_validacao)).write_pdf()
