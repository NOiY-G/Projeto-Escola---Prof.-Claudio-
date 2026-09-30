import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.financeiro import services as financeiro
from apps.turmas.models import DIA_PARA_WEEKDAY, Turma
from apps.turmas.services import vagas_livres

from .models import Frequencia, Matricula

# Status em que a matrícula ainda "segura" o aluno na turma.
STATUS_EM_ABERTO = (Matricula.Status.ATIVA, Matricula.Status.LISTA_ESPERA)
# Turmas em que uma vaga aberta pode ser preenchida pela fila.
STATUS_TURMA_PREENCHE_VAGA = (Turma.Status.INSCRICOES_ABERTAS, Turma.Status.EM_ANDAMENTO)


class MatriculaErro(ValidationError):
    """Uma regra de matrícula impediu a operação."""


# Horários


def horarios_conflitam(a: Turma, b: Turma) -> bool:
    """Duas turmas conflitam se têm aula no mesmo dia, em horários que se sobrepõem."""
    if not (a.hora_inicio < b.hora_fim and b.hora_inicio < a.hora_fim):
        return False
    inicio = max(a.data_inicio, b.data_inicio)
    fim = min(a.data_fim, b.data_fim)
    if inicio > fim:
        return False
    dias_comuns = set(a.dias_semana_lista) & set(b.dias_semana_lista)
    if not dias_comuns:
        return False
    # Confere se algum dia em comum cai dentro do período compartilhado.
    weekdays = {DIA_PARA_WEEKDAY[d] for d in dias_comuns}
    dias_no_periodo = min((fim - inicio).days + 1, 7)
    return any(
        (inicio + datetime.timedelta(days=i)).weekday() in weekdays for i in range(dias_no_periodo)
    )


def conflitos_de_horario(aluno, turma):
    """Matrículas ativas do aluno em outras turmas com horário conflitante."""
    ativas = (
        Matricula.objects.filter(aluno=aluno, status=Matricula.Status.ATIVA)
        .exclude(turma=turma)
        .select_related("turma")
    )
    return [m for m in ativas if horarios_conflitam(m.turma, turma)]


# Fila de espera


def lista_espera(turma):
    """Fila da turma, na ordem de chegada."""
    return (
        turma.matriculas.filter(status=Matricula.Status.LISTA_ESPERA)
        .select_related("aluno")
        .order_by("data", "pk")
    )


def posicao_na_fila(matricula):
    if matricula.status != Matricula.Status.LISTA_ESPERA:
        return None
    ids = list(lista_espera(matricula.turma).values_list("pk", flat=True))
    return ids.index(matricula.pk) + 1


def preencher_vagas(turma):
    """Promove a `ativa` os primeiros da fila enquanto houver vaga.

    Quem teria conflito de horário com outra matrícula ativa continua na fila.
    Retorna as matrículas promovidas.
    """
    promovidas = []
    if turma.status not in STATUS_TURMA_PREENCHE_VAGA:
        return promovidas
    livres = vagas_livres(turma)
    for matricula in lista_espera(turma):
        if livres <= 0:
            break
        if conflitos_de_horario(matricula.aluno, turma):
            continue
        matricula.status = Matricula.Status.ATIVA
        matricula.save(update_fields=["status"])
        financeiro.gerar_parcelas(matricula)
        promovidas.append(matricula)
        livres -= 1
    return promovidas


# Operações


@transaction.atomic
def matricular(aluno, turma, desconto=Decimal("0")) -> Matricula:
    """Matricula o aluno: `ativa` se houver vaga, senão `lista_espera`.

    As mensalidades do curso são geradas quando a matrícula fica ativa.
    """
    # Trava a turma para que duas matrículas simultâneas não peguem a mesma vaga.
    turma = Turma.objects.select_for_update().get(pk=turma.pk)

    if turma.status != Turma.Status.INSCRICOES_ABERTAS:
        raise MatriculaErro(
            f"A turma {turma.codigo} não está com inscrições abertas "
            f"({turma.get_status_display().lower()})."
        )

    existente = Matricula.objects.filter(aluno=aluno, turma=turma).first()
    if existente and existente.status not in (
        Matricula.Status.CANCELADA,
        Matricula.Status.DESISTENTE,
    ):
        raise MatriculaErro(
            f"{aluno.nome} já tem matrícula nesta turma ({existente.get_status_display().lower()})."
        )

    conflitos = conflitos_de_horario(aluno, turma)
    if conflitos:
        codigos = ", ".join(m.turma.codigo for m in conflitos)
        raise MatriculaErro(
            f"{aluno.nome} já está matriculado(a) em turma com horário conflitante: {codigos}."
        )

    desconto = Decimal(desconto)
    if not Decimal("0") <= desconto <= Decimal("100"):
        raise MatriculaErro("O desconto deve estar entre 0% e 100%.")

    status = Matricula.Status.ATIVA if vagas_livres(turma) > 0 else Matricula.Status.LISTA_ESPERA
    matricula = existente or Matricula(aluno=aluno, turma=turma)
    matricula.desconto = desconto
    # Uma rematrícula entra no fim da fila, como qualquer pedido novo.
    matricula.data = timezone.now()
    matricula.status = status
    matricula.save()
    if status == Matricula.Status.ATIVA:
        financeiro.gerar_parcelas(matricula)
    return matricula


def _encerrar(matricula, novo_status):
    with transaction.atomic():
        matricula = Matricula.objects.select_related("turma").get(pk=matricula.pk)
        turma = Turma.objects.select_for_update().get(pk=matricula.turma_id)
        if matricula.status not in STATUS_EM_ABERTO:
            raise MatriculaErro(
                f"Não é possível alterar uma matrícula {matricula.get_status_display().lower()}."
            )
        liberou_vaga = matricula.status == Matricula.Status.ATIVA
        matricula.status = novo_status
        matricula.save(update_fields=["status"])
        financeiro.cancelar_parcelas_futuras(matricula)
        promovidas = preencher_vagas(turma) if liberou_vaga else []
    return matricula, promovidas


def cancelar(matricula):
    """Cancela a matrícula; se era ativa, a vaga vai para o primeiro da fila."""
    return _encerrar(matricula, Matricula.Status.CANCELADA)


def registrar_desistencia(matricula):
    """Registra a desistência; se era ativa, a vaga vai para o primeiro da fila."""
    return _encerrar(matricula, Matricula.Status.DESISTENTE)


def matriculas_do_usuario(usuario):
    """Matrículas do aluno ligado ao usuário (perfil Aluno)."""
    aluno = getattr(usuario, "aluno", None)
    if aluno is None:
        return Matricula.objects.none()
    return aluno.matriculas.select_related("turma__curso", "certificado").order_by("-data")


def filas_de_espera():
    """Turmas que têm fila, cada uma com a sua lista em ordem de chegada."""
    matriculas = (
        Matricula.objects.filter(status=Matricula.Status.LISTA_ESPERA)
        .select_related("aluno", "turma__curso")
        .order_by("turma__codigo", "data", "pk")
    )
    filas = {}
    for matricula in matriculas:
        filas.setdefault(matricula.turma, []).append(matricula)
    return filas


# Chamada e frequência


def aulas_realizadas(turma, hoje=None):
    """Aulas cuja data já chegou (hoje inclusive)."""
    hoje = hoje or timezone.localdate()
    return turma.aulas.filter(data__lte=hoje)


def aula_padrao(turma, hoje=None):
    """A aula que a chamada abre: a de hoje, senão a última que passou, senão a primeira."""
    hoje = hoje or timezone.localdate()
    return (
        turma.aulas.filter(data__lte=hoje).order_by("-data").first()
        or turma.aulas.order_by("data").first()
    )


def chamada_da_aula(aula):
    """Linhas da chamada: cada matrícula ativa com a frequência já gravada (ou None).

    Em turma encerrada não há mais matrículas ativas; mostramos quem tem registro.
    """
    gravadas = {f.matricula_id: f for f in aula.frequencias.select_related("matricula__aluno")}
    if aula.turma.status in (Turma.Status.CONCLUIDA, Turma.Status.CANCELADA):
        linhas = sorted(gravadas.values(), key=lambda f: f.matricula.aluno.nome)
        return [(f.matricula, f) for f in linhas]
    return [(m, gravadas.get(m.pk)) for m in matriculas_da_chamada(aula.turma)]


def matriculas_da_chamada(turma):
    """Quem aparece na chamada: as matrículas ativas, em ordem alfabética."""
    return (
        turma.matriculas.filter(status=Matricula.Status.ATIVA)
        .select_related("aluno")
        .order_by("aluno__nome")
    )


@transaction.atomic
def registrar_chamada(aula, presentes, observacoes=None, conteudo=None, hoje=None):
    """Grava a presença de todas as matrículas ativas da turma nesta aula.

    `presentes` são os ids das matrículas presentes; quem não estiver lá fica
    com falta. `observacoes` é um dict {id da matrícula: texto}.
    """
    hoje = hoje or timezone.localdate()
    if aula.data > hoje:
        raise MatriculaErro("Não é possível fazer a chamada de uma aula que ainda não aconteceu.")
    # Relê a turma travada: ela pode ter sido concluída depois que a tela abriu.
    turma = Turma.objects.select_for_update().get(pk=aula.turma_id)
    if turma.status in (Turma.Status.CONCLUIDA, Turma.Status.CANCELADA):
        raise MatriculaErro(
            f"A turma está {turma.get_status_display().lower()}; a chamada não pode mais ser alterada."
        )
    presentes = {int(pk) for pk in presentes}
    observacoes = {int(pk): (texto or "").strip() for pk, texto in (observacoes or {}).items()}

    matriculas = list(matriculas_da_chamada(turma))
    desconhecidas = presentes - {m.pk for m in matriculas}
    if desconhecidas:
        raise MatriculaErro("A chamada tem alunos que não estão ativos nesta turma.")

    frequencias = []
    for matricula in matriculas:
        frequencia, _ = Frequencia.objects.update_or_create(
            matricula=matricula,
            aula=aula,
            defaults={
                "presente": matricula.pk in presentes,
                "observacao": observacoes.get(matricula.pk, "")[:255],
            },
        )
        frequencias.append(frequencia)

    if conteudo is not None:
        aula.conteudo = conteudo.strip()
        aula.save(update_fields=["conteudo"])
    return frequencias


def percentual_frequencia(matricula, hoje=None):
    """Regra 4: presenças / aulas já realizadas × 100.

    Aula realizada é a que tem data até hoje; sem chamada registrada conta como
    falta. Retorna None se a turma ainda não teve aula.
    """
    realizadas = aulas_realizadas(matricula.turma, hoje)
    total = realizadas.count()
    if total == 0:
        return None
    presencas = matricula.frequencias.filter(aula__in=realizadas, presente=True).count()
    return round(presencas * 100 / total, 1)


def resumo_frequencia(turma, hoje=None):
    """{id da matrícula: percentual} para todas as matrículas da turma."""
    realizadas = list(aulas_realizadas(turma, hoje).values_list("pk", flat=True))
    if not realizadas:
        return {}
    presencas = dict(
        Frequencia.objects.filter(matricula__turma=turma, aula_id__in=realizadas, presente=True)
        .values_list("matricula_id")
        .annotate(total=models.Count("pk"))
    )
    return {
        pk: round(presencas.get(pk, 0) * 100 / len(realizadas), 1)
        for pk in turma.matriculas.values_list("pk", flat=True)
    }
