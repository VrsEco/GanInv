import os
import uuid
from dataclasses import dataclass
from pathlib import Path


CATEGORY_ALIASES = {
    'Matrícula': 'Matricula',
    'matrícula': 'Matricula',
    'matricula': 'Matricula',
    'certidao': 'Matricula',
    'certidão': 'Matricula',
    'edital': 'Edital',
    'outros': 'Outros',
    'foto': 'Foto',
}

CATEGORY_DIRECTORY_MAP = {
    'Edital': 'edital',
    'Matricula': 'matricula',
    'Outros': 'outros',
    'Foto': 'foto',
}

IMAGE_CATEGORIES = {'Foto'}
SINGLE_FILE_CATEGORIES = {'Edital', 'Matricula'}

IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
DOCUMENT_EXTENSIONS = {'pdf', 'doc', 'docx'}


class UploadValidationError(ValueError):
    pass


class UploadTooLargeError(UploadValidationError):
    pass


@dataclass
class SavedUpload:
    category: str
    original_filename: str
    stored_filename: str
    relative_path: str
    absolute_path: str
    mime_type: str
    extension: str
    size_bytes: int


def normalize_category(category: str) -> str:
    raw = (category or 'Outros').strip()
    if not raw:
        return 'Outros'

    if raw in CATEGORY_DIRECTORY_MAP:
        return raw

    return CATEGORY_ALIASES.get(raw.lower(), raw)


def is_single_file_category(category: str) -> bool:
    return normalize_category(category) in SINGLE_FILE_CATEGORIES


def get_allowed_extensions(category: str) -> set[str]:
    normalized = normalize_category(category)
    if normalized in IMAGE_CATEGORIES:
        return IMAGE_EXTENSIONS
    return DOCUMENT_EXTENSIONS


def get_file_size(file_storage) -> int:
    stream = file_storage.stream
    current_pos = stream.tell()
    stream.seek(0, os.SEEK_END)
    size_bytes = stream.tell()
    stream.seek(current_pos)
    return size_bytes


def validate_file(file_storage, category: str, max_size_bytes: int) -> tuple[str, str, int]:
    filename = (file_storage.filename or '').strip()
    if not filename:
        raise UploadValidationError('Nome do arquivo vazio.')

    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if not extension:
        raise UploadValidationError('O arquivo precisa ter uma extensão válida.')

    allowed_extensions = get_allowed_extensions(category)
    if extension not in allowed_extensions:
        allowed_list = ', '.join(sorted(allowed_extensions))
        raise UploadValidationError(f'Tipo de arquivo não permitido para {normalize_category(category)}. Permitidos: {allowed_list}.')

    size_bytes = get_file_size(file_storage)
    if size_bytes <= 0:
        raise UploadValidationError('Arquivo vazio não é permitido.')

    if size_bytes > max_size_bytes:
        max_size_mb = round(max_size_bytes / (1024 * 1024), 2)
        raise UploadTooLargeError(f'Arquivo excede o limite de {max_size_mb} MB.')

    mime_type = (file_storage.mimetype or '').strip() or 'application/octet-stream'
    return extension, mime_type, size_bytes


def build_relative_path(company_id: int, imovel_id: int, category: str, extension: str, anexo_id: int | None = None) -> str:
    normalized = normalize_category(category)
    category_dir = CATEGORY_DIRECTORY_MAP.get(normalized, 'outros')
    unique_suffix = f'{anexo_id}_{uuid.uuid4().hex}' if anexo_id else uuid.uuid4().hex
    filename = f'{unique_suffix}.{extension}'
    return str(Path(f'company_{company_id}') / f'imovel_{imovel_id}' / category_dir / filename)


def ensure_upload_root(upload_root: str) -> str:
    root = Path(upload_root)
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def resolve_absolute_path(upload_root: str, relative_path: str) -> str:
    root = Path(upload_root).resolve()
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise UploadValidationError('Caminho de storage inválido.')
    return str(candidate)


def save_upload(file_storage, *, upload_root: str, company_id: int, imovel_id: int, category: str, max_size_bytes: int, anexo_id: int | None = None) -> SavedUpload:
    normalized = normalize_category(category)
    extension, mime_type, size_bytes = validate_file(file_storage, normalized, max_size_bytes)
    relative_path = build_relative_path(company_id=company_id, imovel_id=imovel_id, category=normalized, extension=extension, anexo_id=anexo_id)
    absolute_path = resolve_absolute_path(upload_root, relative_path)

    Path(absolute_path).parent.mkdir(parents=True, exist_ok=True)
    file_storage.stream.seek(0)
    file_storage.save(absolute_path)

    return SavedUpload(
        category=normalized,
        original_filename=file_storage.filename,
        stored_filename=os.path.basename(absolute_path),
        relative_path=relative_path.replace('\\', '/'),
        absolute_path=absolute_path,
        mime_type=mime_type,
        extension=extension,
        size_bytes=size_bytes,
    )


def delete_physical_file(upload_root: str, relative_path: str | None) -> bool:
    if not relative_path:
        return False

    absolute_path = resolve_absolute_path(upload_root, relative_path)
    target = Path(absolute_path)
    if not target.exists():
        return False

    target.unlink()
    return True


def format_size_bytes(size_bytes: int | None) -> str:
    size = int(size_bytes or 0)
    if size <= 0:
        return '0 B'

    units = ['B', 'KB', 'MB', 'GB']
    unit_index = 0
    value = float(size)
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f'{int(value)} {units[unit_index]}'

    return f'{value:.1f} {units[unit_index]}'
