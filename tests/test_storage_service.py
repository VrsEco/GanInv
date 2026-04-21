from io import BytesIO

from werkzeug.datastructures import FileStorage

from src.core.services.storage_service import (
    UploadValidationError,
    delete_physical_file,
    normalize_category,
    resolve_absolute_path,
    save_upload,
)


def make_file(filename: str, content: bytes, mimetype: str) -> FileStorage:
    return FileStorage(
        stream=BytesIO(content),
        filename=filename,
        content_type=mimetype,
    )


def test_normalize_category_supports_aliases():
    assert normalize_category('Matrícula') == 'Matricula'
    assert normalize_category('foto') == 'Foto'
    assert normalize_category('Outros') == 'Outros'


def test_save_upload_persists_under_expected_tree(tmp_path):
    file_storage = make_file('edital.pdf', b'arquivo de teste', 'application/pdf')

    saved = save_upload(
        file_storage,
        upload_root=str(tmp_path),
        company_id=7,
        imovel_id=99,
        category='Edital',
        max_size_bytes=1024 * 1024,
        anexo_id=123,
    )

    assert saved.category == 'Edital'
    assert saved.relative_path.startswith('company_7/imovel_99/edital/')
    assert saved.relative_path.endswith('.pdf')
    assert tmp_path.joinpath(saved.relative_path).exists()


def test_save_upload_rejects_oversized_file(tmp_path):
    file_storage = make_file('foto.jpg', b'a' * 20, 'image/jpeg')

    try:
        save_upload(
            file_storage,
            upload_root=str(tmp_path),
            company_id=1,
            imovel_id=1,
            category='Foto',
            max_size_bytes=10,
        )
        assert False, 'Era esperado UploadValidationError para arquivo acima do limite'
    except UploadValidationError as exc:
        assert 'limite' in str(exc)


def test_delete_physical_file_removes_saved_file(tmp_path):
    file_storage = make_file('foto.png', b'png-data', 'image/png')
    saved = save_upload(
        file_storage,
        upload_root=str(tmp_path),
        company_id=1,
        imovel_id=2,
        category='Foto',
        max_size_bytes=1024 * 1024,
        anexo_id=1,
    )

    assert delete_physical_file(str(tmp_path), saved.relative_path) is True
    assert not tmp_path.joinpath(saved.relative_path).exists()


def test_resolve_absolute_path_blocks_escape(tmp_path):
    try:
        resolve_absolute_path(str(tmp_path), '../fora.pdf')
        assert False, 'Era esperado bloqueio de path traversal'
    except UploadValidationError as exc:
        assert 'inválido' in str(exc)
