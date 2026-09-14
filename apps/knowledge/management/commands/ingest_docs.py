from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.knowledge.services.ingest import ingest_document, ingest_all


class Command(BaseCommand):
    help = 'Ingest policy documents into the knowledge base. Default: ingest all .md/.pdf files in knowledge/.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to a single markdown or PDF file to ingest (overwrites the store).',
        )
        parser.add_argument(
            '--pdf-knowledge-only',
            action='store_true',
            help='Ingest only PDF files from knowledge/pdf-knowledge/.',
        )

    def handle(self, *args, **options):
        single = options['file']
        pdf_only = options['pdf_knowledge_only']

        if single:
            path = Path(single)
            if not path.exists():
                self.stderr.write(self.style.ERROR(f'File not found: {path}'))
                return
            self.stdout.write(f'Ingesting single file: {path}')
            count = ingest_document(str(path))
            self.stdout.write(self.style.SUCCESS(f'Ingested {count} chunks from {path.name}.'))
            self._print_paths()
            return

        if pdf_only:
            pdf_dir = settings.KNOWLEDGE_DIR / 'pdf-knowledge'
            self.stdout.write(f'Ingesting only PDF knowledge files in {pdf_dir}...')
            summary = ingest_all(knowledge_dir=pdf_dir, include_md=False, include_pdf=True)
        else:
            self.stdout.write(f'Ingesting all markdown/PDF files in {settings.KNOWLEDGE_DIR}...')
            summary = ingest_all()
        self.stdout.write(self.style.SUCCESS(
            f'Ingested {summary["n_chunks"]} chunks from {summary["n_docs"]} documents.'
        ))
        for doc, count in summary['per_doc'].items():
            self.stdout.write(f'  {count:>3} chunks  |  {doc}')
        self._print_paths()

    def _print_paths(self):
        self.stdout.write(f'\nchunks.json    -> {settings.DATA_DIR / "chunks.json"}')
        self.stdout.write(f'embeddings.npy -> {settings.DATA_DIR / "embeddings.npy"}')
