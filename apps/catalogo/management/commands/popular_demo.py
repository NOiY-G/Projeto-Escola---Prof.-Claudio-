"""Popula o banco com dados de exemplo para demonstração.

Uso:
    python manage.py popular_demo            # banco vazio
    python manage.py popular_demo --limpar   # apaga os dados atuais e recria

As datas são relativas a hoje, para a demonstração sempre ter uma turma
concluída, uma em andamento e turmas com inscrições abertas.
"""

import datetime
import io
import random
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso, Instrutor
from apps.catalogo.services import criar_instrutor
from apps.certificados.models import Certificado
from apps.certificados.services import concluir_turma
from apps.contas.services import GRUPO_ADMINISTRADOR, GRUPO_ALUNO, atribuir_perfil
from apps.financeiro import services as financeiro
from apps.financeiro.models import Comprovante, Pagamento, Parcela
from apps.matriculas import services as matriculas
from apps.matriculas.models import Frequencia, Matricula
from apps.turmas.models import Aula, Feriado, Turma
from apps.turmas.services import cadastrar_feriados_nacionais, data_fim_sugerida, gerar_aulas, somar_meses

SENHA_PADRAO = "demo1234"

CURSOS = [
    {
        "nome": "Informática Básica",
        "carga_horaria": 40,
        "duracao_meses": 3,
        "horas_por_aula": Decimal("2"),
        "valor_mensalidade": Decimal("0"),
        "frequencia_minima": 75,
        "descricao": "Primeiros passos no computador: mouse, teclado, pastas e arquivos, "
        "editor de textos e navegação na internet.",
        "pre_requisitos": "",
    },
    {
        "nome": "Excel",
        "carga_horaria": 30,
        "duracao_meses": 2,
        "horas_por_aula": Decimal("2"),
        "valor_mensalidade": Decimal("75.00"),
        "frequencia_minima": 75,
        "descricao": "Planilhas do básico ao intermediário: fórmulas, funções, gráficos e "
        "tabelas dinâmicas.",
        "pre_requisitos": "Informática Básica ou conhecimento equivalente.",
    },
    {
        "nome": "Digitação",
        "carga_horaria": 20,
        "duracao_meses": 3,
        "horas_por_aula": Decimal("2"),
        "valor_mensalidade": Decimal("40.00"),
        "frequencia_minima": 70,
        "descricao": "Digitação com os dez dedos, postura correta e ganho de velocidade.",
        "pre_requisitos": "",
    },
    {
        "nome": "Internet Segura",
        "carga_horaria": 12,
        "duracao_meses": 1,
        "horas_por_aula": Decimal("3"),
        "valor_mensalidade": Decimal("0"),
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
        Pagamento.objects.all().delete()
        for comprovante in Comprovante.objects.all():
            comprovante.arquivo.delete(save=False)
        Comprovante.objects.all().delete()
        Parcela.objects.all().delete()
        Certificado.objects.all().delete()
        Frequencia.objects.all().delete()
        Matricula.objects.all().delete()
        Aula.objects.all().delete()
        Turma.objects.all().delete()
        Feriado.objects.all().delete()
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
        # Feriados antes das turmas: as aulas já são geradas sem eles.
        for ano in (self.hoje.year - 1, self.hoje.year, self.hoje.year + 1):
            cadastrar_feriados_nacionais(ano)
        self.cursos = {c["nome"]: Curso.objects.create(**c) for c in CURSOS}
        self.instrutores = {
            i["username"]: criar_instrutor(senha=self.senha, **i) for i in INSTRUTORES
        }
        self._criar_admin()
        self.alunos = self._criar_alunos()
        self._criar_usuario_aluno()
        self._criar_turmas()

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

    def _turma(self, codigo, curso, instrutor, inicio, dias, hora, vagas, sala):
        """Turma com a duração do curso e aulas do tamanho definido no curso."""
        curso = self.cursos[curso]
        comeco = datetime.datetime.combine(inicio, datetime.time(hora))
        turma = Turma.objects.create(
            codigo=codigo,
            curso=curso,
            instrutor=self.instrutores[instrutor],
            data_inicio=inicio,
            data_fim=data_fim_sugerida(curso, inicio),
            dias_semana=dias,
            hora_inicio=comeco.time(),
            hora_fim=(comeco + datetime.timedelta(hours=float(curso.horas_por_aula))).time(),
            vagas=vagas,
            sala=sala,
            status=Turma.Status.INSCRICOES_ABERTAS,
        )
        gerar_aulas(turma)
        return turma

    def _matricular(self, turma, alunos, dias_antes_do_inicio=20, descontos=None):
        """Matricula pelos serviços (vagas, fila, conflito de horário e parcelas valem)."""
        feitas = []
        descontos = descontos or {}
        for i, aluno in enumerate(alunos):
            try:
                matricula = matriculas.matricular(
                    aluno, turma, desconto=descontos.get(i, Decimal("0"))
                )
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

        # 1) Informática Básica (3 meses) concluída há umas duas semanas, com certificados.
        inicio = somar_meses(segunda, -3) - datetime.timedelta(weeks=2)
        t1 = self._turma(f"INF-{inicio.year}-01", "Informática Básica", "maria", inicio, "seg,qua", 8, 12, "Laboratório 1")
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
        t2 = self._turma(f"INF-{inicio.year}-02", "Informática Básica", "maria", inicio, "ter,qui", 14, 10, "Laboratório 1")
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
        t3 = self._turma(f"EXC-{inicio.year}-01", "Excel", "carlos", inicio, "seg,qua", 18, 15, "Laboratório 2")
        # Quem já fez Informática; com uma bolsa de 50%.
        self._matricular(t3, a[0:9], dias_antes_do_inicio=13, descontos={4: Decimal("50")})

        # 4) Digitação com inscrições abertas, turma pequena já cheia e com fila.
        inicio = segunda + datetime.timedelta(weeks=1)
        t4 = self._turma(f"DIG-{inicio.year}-01", "Digitação", "carlos", inicio, "ter,qui", 9, 6, "Laboratório 2")
        self._matricular(t4, a[20:30], dias_antes_do_inicio=6)

        # 5) Internet Segura planejada para o mês que vem (sem inscrições ainda).
        inicio = segunda + datetime.timedelta(weeks=5)
        t5 = self._turma(f"NET-{inicio.year}-01", "Internet Segura", "maria", inicio, "qua,sab", 9, 20, "Auditório")
        Turma.objects.filter(pk=t5.pk).update(status=Turma.Status.PLANEJADA)

        # 6) Excel cancelada por falta de inscritos.
        inicio = segunda - datetime.timedelta(weeks=6)
        t6 = self._turma(f"EXC-{inicio.year}-00", "Excel", "carlos", inicio, "qua,sab", 8, 15, "Laboratório 2")
        for matricula in self._matricular(t6, a[25:28]):
            matriculas.cancelar(matricula)
        Turma.objects.filter(pk=t6.pk).update(status=Turma.Status.CANCELADA)

        # 7) Digitação em andamento (paga, 3 mensalidades): um aluno em cada situação de pagamento.
        # Começou há um mês e poucos dias: a 2ª mensalidade venceu há uns 3 dias.
        inicio = somar_meses(hoje, -1) - datetime.timedelta(days=3)
        t7 = self._turma(f"DIG-{inicio.year}-00", "Digitação", "carlos", inicio, "sex", 18, 8, "Laboratório 2")
        self._pagamentos_da_turma_em_andamento(t7, [a[0]] + a[9:16])
        Turma.objects.filter(pk=t7.pk).update(status=Turma.Status.EM_ANDAMENTO)
        t7.refresh_from_db()
        self._fazer_chamadas(t7, {aluno.pk: 0.9 for aluno in a}, ["Postura e teclas guia", "Fileira de cima", "Fileira de baixo", "Números", "Velocidade"])

    def _pagamentos_da_turma_em_andamento(self, turma, alunos):
        """Matrículas feitas antes do início, com mensalidades vencendo a partir do 1º dia de aula."""
        # (desconto, o que aconteceu com cada mensalidade; a 3ª ainda vai vencer)
        planos = [
            (0, ["pix", None]),                  # aluno de login: 2ª vencida há poucos dias (pendente)
            (0, ["dinheiro", "pix"]),            # em dia
            (0, ["pix", "pix", "pix"]),          # adiantou a última: em dia
            (0, [None, None]),                   # nada pago: inadimplente
            (0, ["pix", "comprovante"]),         # 2ª com comprovante esperando conferência
            (100, []),                           # bolsa integral: isento
            (50, ["dinheiro", "dinheiro"]),      # meia bolsa, em dia
            (0, ["pix", "recusado"]),            # comprovante recusado: pendente
        ]
        admin = User.objects.get(username="admin")
        for i, (aluno, (desconto, eventos)) in enumerate(zip(alunos, planos)):
            matricula = self._matricular(turma, [aluno], descontos={0: Decimal(desconto)})[0]
            # Como se a matrícula tivesse sido feita antes do início: todas as mensalidades.
            matricula.parcelas.all().delete()
            financeiro.gerar_parcelas(matricula, hoje=turma.data_inicio)
            parcelas = list(matricula.parcelas.order_by("numero"))
            for parcela, evento in zip(parcelas, eventos):
                pago_em = min(parcela.vencimento + datetime.timedelta(days=1), self.hoje)
                if evento in ("pix", "dinheiro"):
                    financeiro.registrar_pagamento(
                        parcela,
                        forma=evento,
                        data=pago_em,
                        recebido_por=admin,
                        codigo_transacao=f"E{self.rng.randint(10**15, 10**16 - 1)}" if evento == "pix" else "",
                    )
                elif evento in ("comprovante", "recusado"):
                    comprovante = financeiro.enviar_comprovante(
                        parcela, self._imagem_de_comprovante(parcela), aluno.usuario or admin
                    )
                    if evento == "recusado":
                        financeiro.recusar_comprovante(
                            comprovante, usuario=admin, motivo="O valor do Pix é diferente do valor da parcela."
                        )

    def _imagem_de_comprovante(self, parcela):
        """Uma imagem simples no lugar de um comprovante de verdade."""
        imagem = Image.new("RGB", (360, 480), "white")
        desenho = ImageDraw.Draw(imagem)
        # Sem acentos: a fonte padrão do Pillow não tem esses caracteres.
        linhas = ["Comprovante de Pix", "(exemplo da demonstracao)", "",
                  f"Valor: R$ {parcela.valor:.2f}".replace(".", ","), f"Identificador: {parcela.identificador}",
                  f"Para: {settings.PIX_NOME_RECEBEDOR}"]
        for n, texto in enumerate(linhas):
            desenho.text((24, 40 + 32 * n), texto, fill="black")
        buffer = io.BytesIO()
        imagem.save(buffer, format="PNG")
        return SimpleUploadedFile("comprovante.png", buffer.getvalue(), content_type="image/png")

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
            f"{Aula.objects.count()} aulas, {Feriado.objects.count()} feriados"
        )
        contagem = {s.label: Matricula.objects.filter(status=s).count() for s in Matricula.Status}
        self.stdout.write("  Matrículas: " + ", ".join(f"{n} {rotulo.lower()}" for rotulo, n in contagem.items()))
        self.stdout.write(f"  {Certificado.objects.count()} certificados emitidos")
        contagem = {}
        for situacao in financeiro.situacoes(Matricula.objects.filter(parcelas__isnull=False).distinct()).values():
            contagem[situacao.rotulo] = contagem.get(situacao.rotulo, 0) + 1
        self.stdout.write(
            f"  {Parcela.objects.count()} mensalidades, {Pagamento.objects.count()} pagamentos, "
            f"{Comprovante.objects.filter(status=Comprovante.Status.EM_ANALISE).count()} comprovante(s) para conferir"
        )
        self.stdout.write("  Situação financeira: " + ", ".join(f"{n} {r.lower()}" for r, n in sorted(contagem.items())) + "\n")
        for turma in Turma.objects.select_related("curso").order_by("data_inicio"):
            self.stdout.write(
                f"  {turma.codigo:<12} {turma.curso.nome:<20} {turma.get_status_display():<19} "
                f"{turma.data_inicio:%d/%m/%Y} a {turma.data_fim:%d/%m/%Y}"
            )
        self.stdout.write(estilo.SUCCESS(f"\nUsuários (senha: {self.senha}):"))
        self.stdout.write("  admin   – Administrador")
        self.stdout.write("  maria   – Instrutora (Informática Básica, Internet Segura)")
        self.stdout.write("  carlos  – Instrutor (Excel, Digitação)")
        self.stdout.write(
            f"  aluno   – Aluno ({self.alunos[0].nome}: tem certificado, matrícula em Excel e "
            "uma mensalidade de Digitação para pagar com Pix)"
        )
