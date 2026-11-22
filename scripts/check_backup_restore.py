"""Isolated synthetic SQLite + private-file encrypted backup/restore drill.

This script never imports the running app or Django settings, reads environment
configuration, or connects to a real database. It exercises the archive contract
with a tiny synthetic patient/document schema, not a production PostgreSQL restore.
All paths and encryption keys are generated in a private temporary directory.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from cryptography.fernet import Fernet, InvalidToken


def exercise_backup_restore():
    with tempfile.TemporaryDirectory(prefix='clinic-synthetic-restore-') as temp:
        directory = Path(temp)
        source = directory / 'source'
        restored = directory / 'restored'
        source.mkdir(mode=0o700)
        restored.mkdir(mode=0o700)
        documents = source / 'private_documents'
        documents.mkdir(mode=0o700)
        document_bytes = b'%PDF-1.7\nSYNTHETIC-RESTORE-DRILL-NOT-A-PATIENT-RECORD\n%%EOF\n'
        document = documents / 'synthetic.pdf'
        document.write_bytes(document_bytes)
        os.chmod(document, 0o600)
        digest = hashlib.sha256(document_bytes).hexdigest()
        with sqlite3.connect(source / 'records.sqlite3') as db:
            db.executescript('CREATE TABLE patients(id TEXT PRIMARY KEY, label TEXT NOT NULL); '
                             'CREATE TABLE documents(id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), '
                             'relative_path TEXT NOT NULL, sha256 TEXT NOT NULL);')
            db.execute('INSERT INTO patients VALUES (?, ?)', ('synthetic-patient', 'Synthetic restore fixture'))
            db.execute('INSERT INTO documents VALUES (?, ?, ?, ?)',
                       ('synthetic-document', 'synthetic-patient', 'private_documents/synthetic.pdf', digest))
            db.commit()
            # A SQLite online backup makes a consistent DB copy; production
            # requires coordinated PostgreSQL/file-volume snapshot procedures.
            with sqlite3.connect(directory / 'database-snapshot.sqlite3') as snapshot:
                db.backup(snapshot)
        payload = io.BytesIO()
        manifest = {'kind': 'clinic-synthetic-drill-v1', 'files': {
            'records.sqlite3': hashlib.sha256((directory / 'database-snapshot.sqlite3').read_bytes()).hexdigest(),
            'private_documents/synthetic.pdf': digest}}
        with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(directory / 'database-snapshot.sqlite3', 'records.sqlite3')
            archive.write(document, 'private_documents/synthetic.pdf')
            archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
        key = Fernet.generate_key()  # Memory only; never printed or retained.
        encrypted = Fernet(key).encrypt(payload.getvalue())
        archive_path = directory / 'synthetic-backup.fernet'
        archive_path.write_bytes(encrypted)
        os.chmod(archive_path, 0o600)
        wrong_key_rejected = False
        try:
            Fernet(Fernet.generate_key()).decrypt(encrypted)
        except InvalidToken:
            wrong_key_rejected = True
        if not wrong_key_rejected:
            raise AssertionError('wrong_key_was_accepted')
        tampered_rejected = False
        tampered = bytearray(encrypted)
        tampered[len(tampered) // 2] ^= 1
        try:
            Fernet(key).decrypt(bytes(tampered))
        except InvalidToken:
            tampered_rejected = True
        if not tampered_rejected:
            raise AssertionError('tampered_archive_was_accepted')
        with zipfile.ZipFile(io.BytesIO(Fernet(key).decrypt(archive_path.read_bytes()))) as archive:
            allowed = {'records.sqlite3', 'private_documents/synthetic.pdf', 'manifest.json'}
            if set(archive.namelist()) != allowed:
                raise AssertionError('unexpected_archive_members')
            for name in allowed:
                target = restored / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(archive.read(name))
                os.chmod(target, 0o600)
        restored_manifest = json.loads((restored / 'manifest.json').read_text())
        for name, expected in restored_manifest['files'].items():
            if hashlib.sha256((restored / name).read_bytes()).hexdigest() != expected:
                raise AssertionError('restored_checksum_mismatch')
        with sqlite3.connect(restored / 'records.sqlite3') as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise AssertionError('restored_database_integrity_failed')
            records = db.execute('SELECT p.id,d.relative_path,d.sha256 FROM patients p JOIN documents d ON d.patient_id=p.id').fetchall()
        if records != [('synthetic-patient', 'private_documents/synthetic.pdf', digest)]:
            raise AssertionError('restored_linked_records_mismatch')
        if (restored / records[0][1]).read_bytes() != document_bytes:
            raise AssertionError('restored_document_bytes_mismatch')
        return {'synthetic_only': True, 'database': 'isolated_sqlite_fixture',
                'restored_linked_records': 1, 'restored_private_files': 1,
                'encrypted_archive': True, 'wrong_key_rejected': wrong_key_rejected,
                'tampering_rejected': tampered_rejected, 'temporary_files_removed_on_exit': True,
                'production_postgresql_restore_verified': False}


if __name__ == '__main__':
    print(json.dumps(exercise_backup_restore(), sort_keys=True))
