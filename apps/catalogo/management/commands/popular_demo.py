"""Popula o banco com dados de exemplo para demonstração.

Uso:
    python manage.py popular_demo            # banco vazio
    python manage.py popular_demo --limpar   # apaga os dados atuais e recria

As datas são relativas a hoje, para a demonstração sempre ter uma turma
concluída, uma em andamento e turmas com inscrições abertas.
"""

import datetime
import random
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso, Instrutor
from apps.catalogo.services import criar_instrutor
from apps.certificados.models import Certificado
from apps.certificados.services import concluir_turma
from apps.contas.services import GRUPO_ADMINISTRADOR, GRUPO_ALUNO, atribuir_perfil
from apps.matriculas import services as matriculas
from apps.matriculas.models import Frequencia, Matricula
from apps.turmas.models import Aula, Turma
from apps.turmas.services import gerar_aulas

SENHA_PADRAO = "demo1234"

CURSOS = [
    {
        "nome": "Informática Básica",
        "carga_horaria": 40,
        "valor": Decimal("0"),
        "frequencia_minima": 75,
        "descricao": "Primeiros passos no computador: mouse, teclado, pastas e arquivos, "
        "editor de textos e navegação na internet.",
        "pre_requisitos": "",
    },
    {
        "nome": "Excel",
        "carga_horaria": 30,
        "valor": Decimal("150.00"),
        "frequencia_minima": 75,
        "descricao": "Planilhas do básico ao intermediário: fórmulas, funções, gráficos e "
        "tabelas dinâmicas.",
        "pre_requisitos": "Informática Básica ou conhecimento equivalente.",
    },
    {
        "nome": "Digitação",
        "carga_horaria": 20,
        "valor": Decimal("80.00"),
        "frequencia_minima": 70,
        "descricao": "Digitação com os dez dedos, postura correta e ganho de velocidade.",
        "pre_requisitos": "",
    },
    {
        "nome": "Internet Segura",
        "carga_horaria": 12,
        "valor": Decimal("0"),
        "frequencia_minima": 75,
        "descricao": "Senhas fortes, golpes comuns, compras on-line, privacidade e uso "
        "seguro do celular e das redes sociais.",
        "pre_requisitos": "",
    },
]

INSTRUTORES = [
    {
        "username": "maria",
        "nome": "Maria Souza",
        "email": "maria@exemplo.com",
        "telefone": "(91) 98111-2233",
        "especialidades": "Informática Básica, Internet Segura",
    },
    {
        "username": "carlos",
        "nome": "Carlos Pereira",
        "email": "carlos@exemplo.com",
        "telefone": "(91) 98444-5566",
        "especialidades": "Excel, Digitação",
    },
]

NOMES = [
    "Ana Beatriz Lima", "Antônio Carlos Rocha", "Beatriz Nascimento", "Bruno Almeida",
    "Camila Ferreira", "Carla Mendes", "Daniel Moreira", "Débora Cardoso", "Eduardo Barbosa",
    "Fernanda Dias", "Francisco Teixeira", "Gabriela Castro", "Helena Martins", "Igor Ribeiro",
    "Joana Pinto", "João Pedro da Silva", "José Raimundo Costa", "Juliana Araújo", "Larissa Gomes",
    "Lucas Oliveira", "Luiza Reis", "Marcos Paulo Santos", "Mariana Freitas", "Paulo Henrique Lopes",
    "Pedro Lima", "Rafaela Monteiro", "Raimunda Sousa", "Rita de Cássia Nunes", "Sebastião Farias",
    "Tiago Alves",
]

ESCOLARIDADES = [e for e, _ in Aluno.Escolaridade.choices]
BAIRROS = ["Umarizal", "Marco", "Pedreira", "Guamá", "Jurunas", "Batista Campos", "Nazaré", "Cremação"]


def gerar_cpf(rng):
    """CPF válido (dígitos verificadores corretos), só para demonstração."""
    base = [rng.randint(0, 9) for _ in range(9)]
    while len(set(base)) == 1:
        base = [rng.randint(0, 9) for _ in range(9)]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(base))
        base.append((soma * 10) % 11 % 10)
    return "".join(map(str, base))


class Command(BaseCommand):
    help = "Cria cursos, instrutores, turmas, alunos, matrículas, chamadas e certificados de exemplo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga TODOS os cursos, turmas, alunos, matrículas e certificados antes de popular.",
        )
        parser.add_argument(
            "--senha", default=SENHA_PADRAO, help=f"Senha dos usuários de demonstração (padrão: {SENHA_PADRAO})."
        )
        parser.add_argument(
            "--permitir-producao",
            action="store_true",
            help="Permite rodar com DEBUG desligado (não recomendado).",
        )

    def handle(self, *args, **opcoes):
        if not settings.DEBUG and not opcoes["permitir_producao"]:
            raise CommandError(
                "DEBUG está desligado (parece produção). Use --permitir-producao se tiver certeza."
            )
        if Curso.objects.exists() or Aluno.objects.exists():
            if not opcoes["limpar"]:
                raise CommandError(
                    "O banco já tem dados. Use --limpar para apagar tudo e recriar a demonstração."
                )
        self.rng = random.Random(2026)
        self.hoje = timezone.localdate()
        self.senha = opcoes["senha"]

        with transaction.atomic():
            if opcoes["limpar"]:
                self._limpar()
            self._popular()
        self._resumo()

    # Limpeza

    def _limpar(self):
        Certificado.objects.all().delete()
        Frequencia.objects.all().delete()
        Matricula.objects.all().delete()
        Aula.objects.all().delete()
        Turma.objects.all().delete()
        Aluno.objects.all().delete()
        usuarios = list(Instrutor.objects.values_list("usuario_id", flat=True))
        Instrutor.objects.all().delete()
        Curso.objects.all().delete()
        demo = ["admin", "aluno"] + [i["username"] for i in INSTRUTORES]
        User.objects.filter(pk__in=usuarios).delete()
        User.objects.filter(username__in=demo, is_superuser=False).delete()
        self.stdout.write("Dados anteriores apagados.")

    # Dados

    def _popular(self):
        self.cursos = {c["nome"]: Curso.objects.create(**c) for c in CURSOS}
        self.instrutores = {
            i["username"]: criar_instrutor(senha=self.senha, **i) for i in INSTRUTORES
        }
        self._criar_admin()
        self.alunos = self._criar_alunos()
        self._criar_turmas()
        self._criar_usuario_aluno()

    def _criar_admin(self):
        if User.objects.filter(username="admin").exists():
            return
        admin = User.objects.create_user(
            "admin", "admin@exemplo.com", self.senha, first_name="Administração", is_staff=True
        )
        atribuir_perfil(admin, GRUPO_ADMINISTRADOR)

    def _criar_alunos(self):
        alunos = []
        cpfs = set()
        for nome in NOMES:
            cpf = gerar_cpf(self.rng)
            while cpf in cpfs:
                cpf = gerar_cpf(self.rng)
            cpfs.add(cpf)
            primeiro = unicodedata.normalize("NFKD", nome.split()[0].lower()).encode("ascii", "ignore").decode()
            alunos.append(
                Aluno.objects.create(
                    nome=nome,
                    cpf=cpf,
                    data_nascimento=datetime.date(self.rng.randint(1960, 2008), self.rng.randint(1, 12), self.rng.randint(1, 28)),
                    telefone=f"(91) 9{self.rng.randint(8000, 9999)}-{self.rng.randint(1000, 9999)}",
                    email=f"{primeiro}{self.rng.randint(1, 99)}@exemplo.com",
                    endereco=f"Rua {self.rng.randint(1, 30)} de Setembro, {self.rng.randint(10, 999)} – {self.rng.choice(BAIRROS)}",
                    escolaridade=self.rng.choice(ESCOLARIDADES),
                )
            )
        return alunos

    def _turma(self, codigo, curso, instrutor, inicio, semanas, dias, hora, vagas, sala):
        turma = Turma.objects.create(
            codigo=codigo,
            curso=self.cursos[curso],
            instrutor=self.instrutores[instrutor],
            data_inicio=inicio,
            data_fim=inicio + datetime.timedelta(weeks=semanas, days=-1),
            dias_semana=dias,
            hora_inicio=datetime.time(hora),
            hora_fim=datetime.time(hora + 2),
            vagas=vagas,
            sala=sala,
            status=Turma.Status.INSCRICOES_ABERTAS,
        )
        gerar_aulas(turma)
        return turma

    def _matricular(self, turma, alunos, dias_antes_do_inicio=20):
        """Matricula pelos serviços (vagas, fila e conflito de horário valem)."""
        feitas = []
        for i, aluno in enumerate(alunos):
            try:
                matricula = matriculas.matricular(aluno, turma)
            except matriculas.MatriculaErro:
                continue
            # Datas de matrícula espalhadas antes do início, na ordem de chegada.
            data = timezone.make_aware(
                datetime.datetime.combine(
                    turma.data_inicio - datetime.timedelta(days=dias_antes_do_inicio - i),
                    datetime.time(9 + i % 8, (i * 7) % 60),
                )
            )
            Matricula.objects.filter(pk=matricula.pk).update(data=min(data, timezone.now()))
            feitas.append(matricula)
        return feitas

    def _fazer_chamadas(self, turma, assiduidade, conteudos):
        """Chamada de todas as aulas até ontem; `assiduidade` = chance de presença por aluno."""
        aulas = list(turma.aulas.filter(data__lt=self.hoje).order_by("data"))
        for n, aula in enumerate(aulas):
            ativas = list(matriculas.matriculas_da_chamada(turma))
            presentes = [m.pk for m in ativas if self.rng.random() < assiduidade.get(m.aluno_id, 0.9)]
            observacoes = {}
            faltosos = [m for m in ativas if m.pk not in presentes]
            if faltosos and self.rng.random() < 0.3:
                observacoes[self.rng.choice(faltosos).pk] = self.rng.choice(
                    ["Avisou que estava doente.", "Falta justificada (trabalho).", "Consulta médica."]
                )
            matriculas.registrar_chamada(
                aula,
                presentes=presentes,
                observacoes=observacoes,
                conteudo=conteudos[n % len(conteudos)],
                hoje=self.hoje,
            )

    def _criar_turmas(self):
        a = self.alunos
        hoje = self.hoje
        segunda = hoje - datetime.timedelta(days=hoje.weekday())

        # 1) Informática Básica concluída há duas semanas, com certificados.
        inicio = segunda - datetime.timedelta(weeks=12)
        t1 = self._turma(f"INF-{inicio.year}-01", "Informática Básica", "maria", inicio, 10, "seg,qua", 8, 12, "Laboratório 1")
        m1 = self._matricular(t1, a[0:12])
        # Dois alunos com pouca frequência: na conclusão, viram desistentes.
        assiduidade = {m.aluno_id: 0.95 for m in m1}
        assiduidade.update({m1[10].aluno_id: 0.4, m1[11].aluno_id: 0.3})
        self._fazer_chamadas(
            t1,
            assiduidade,
            ["Ligando o computador; mouse e teclado", "Pastas e arquivos", "Editor de textos",
             "Navegador e buscas", "E-mail", "Revisão e exercícios"],
        )
        Turma.objects.filter(pk=t1.pk).update(status=Turma.Status.EM_ANDAMENTO)
        t1.refresh_from_db()
        concluir_turma(t1, hoje=t1.data_fim)

        # 2) Informática Básica em andamento, lotada e com fila; uma desistência promoveu alguém.
        inicio = segunda - datetime.timedelta(weeks=4)
        t2 = self._turma(f"INF-{inicio.year}-02", "Informática Básica", "maria", inicio, 8, "ter,qui", 14, 10, "Laboratório 1")
        m2 = self._matricular(t2, a[12:25])  # 13 pedidos para 10 vagas: 3 na fila
        matriculas.registrar_desistencia(m2[3])  # abre vaga: o 1º da fila é chamado
        Turma.objects.filter(pk=t2.pk).update(status=Turma.Status.EM_ANDAMENTO)
        t2.refresh_from_db()
        self._fazer_chamadas(
            t2,
            {m.aluno_id: 0.85 for m in m2},
            ["Conhecendo o computador", "Mouse e teclado", "Pastas e arquivos", "Editor de textos"],
        )

        # 3) Excel com inscrições abertas (começa em duas semanas), noite.
        inicio = segunda + datetime.timedelta(weeks=2)
        t3 = self._turma(f"EXC-{inicio.year}-01", "Excel", "carlos", inicio, 8, "seg,qua", 18, 15, "Laboratório 2")
        self._matricular(t3, a[0:9], dias_antes_do_inicio=13)  # quem já fez Informática

        # 4) Digitação com inscrições abertas, turma pequena já cheia e com fila.
        inicio = segunda + datetime.timedelta(weeks=1)
        t4 = self._turma(f"DIG-{inicio.year}-01", "Digitação", "carlos", inicio, 5, "ter,qui", 9, 6, "Laboratório 2")
        self._matricular(t4, a[20:30], dias_antes_do_inicio=6)

        # 5) Internet Segura planejada para o mês que vem (sem inscrições ainda).
        inicio = segunda + datetime.timedelta(weeks=5)
        t5 = self._turma(f"NET-{inicio.year}-01", "Internet Segura", "maria", inicio, 3, "sab", 9, 20, "Auditório")
        Turma.objects.filter(pk=t5.pk).update(status=Turma.Status.PLANEJADA)

        # 6) Excel cancelada por falta de inscritos.
        inicio = segunda - datetime.timedelta(weeks=6)
        t6 = self._turma(f"EXC-{inicio.year}-00", "Excel", "carlos", inicio, 8, "sab", 8, 15, "Laboratório 2")
        for matricula in self._matricular(t6, a[25:28]):
            matriculas.cancelar(matricula)
        Turma.objects.filter(pk=t6.pk).update(status=Turma.Status.CANCELADA)

    def _criar_usuario_aluno(self):
        """Login de aluno ligado a quem concluiu Informática e está inscrito em Excel."""
        usuario = User.objects.create_user("aluno", "aluno@exemplo.com", self.senha)
        aluno = self.alunos[0]
        partes = aluno.nome.split(maxsplit=1)
        usuario.first_name, usuario.last_name = partes[0], partes[1] if len(partes) > 1 else ""
        usuario.save()
        atribuir_perfil(usuario, GRUPO_ALUNO)
        aluno.usuario = usuario
        aluno.save()

    # Saída

    def _resumo(self):
        estilo = self.style
        self.stdout.write(estilo.SUCCESS("\nDemonstração criada."))
        self.stdout.write(
            f"  {Curso.objects.count()} cursos, {Instrutor.objects.count()} instrutores, "
            f"{Aluno.objects.count()} alunos, {Turma.objects.count()} turmas, "
            f"{Aula.objects.count()} aulas"
        )
        contagem = {s.label: Matricula.objects.filter(status=s).count() for s in Matricula.Status}
        self.stdout.write("  Matrículas: " + ", ".join(f"{n} {rotulo.lower()}" for rotulo, n in contagem.items()))
        self.stdout.write(f"  {Certificado.objects.count()} certificados emitidos\n")
        for turma in Turma.objects.select_related("curso").order_by("data_inicio"):
            self.stdout.write(
                f"  {turma.codigo:<12} {turma.curso.nome:<20} {turma.get_status_display():<19} "
                f"{turma.data_inicio:%d/%m/%Y} a {turma.data_fim:%d/%m/%Y}"
            )
        self.stdout.write(estilo.SUCCESS(f"\nUsuários (senha: {self.senha}):"))
        self.stdout.write("  admin   – Administrador")
        self.stdout.write("  maria   – Instrutora (Informática Básica, Internet Segura)")
        self.stdout.write("  carlos  – Instrutor (Excel, Digitação)")
        self.stdout.write(f"  aluno   – Aluno ({self.alunos[0].nome}: tem certificado e matrícula em Excel)")
