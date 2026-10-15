"""Private submitted inputs over existing managed storage and conversation authority."""
import base64
import json
import subprocess
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import zipfile
from xml.etree import ElementTree

from PIL import Image
from pypdf import PdfReader

from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from .repository import ConversationRepository
from .contracts import InputError, ConflictError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT = 60000
MAX_FILES = 4


def inspect_input(name, content):
    """Reject unsupported/partial extraction instead of silently clipping input."""
    if not content or len(content) > MAX_FILE_BYTES:
        raise InputError("Attachments must contain 1 byte to 5 MiB.")
    suffix = Path(name).suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > 16_000_000:
                    raise ValueError('Unsupported image or pixel budget')
                mime = Image.MIME[image.format]
                image.verify()
        except Exception:
            raise InputError("Use a valid PNG, JPEG or WebP image within 16 megapixels.") from None
        return mime, None, 'image'
    try:
        if suffix in {'.txt', '.md', '.csv'}:
            text = content.decode('utf-8')
            mime, coverage = 'text/plain', 'complete_text'
        elif suffix == '.pdf':
            if not content.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF')
            document = PdfReader(BytesIO(content), strict=True)
            if document.is_encrypted or len(document.pages) > 30:
                raise ValueError('Encrypted or oversized PDF')
            pages = [page.extract_text() or '' for page in document.pages]
            if any(not page.strip() for page in pages):
                raise ValueError('Scanned page requires vision')
            text = '\n'.join(f'[Page {i+1}]\n{page}' for i, page in enumerate(pages))
            mime, coverage = 'application/pdf', 'text_only_no_visuals'
        elif suffix == '.docx':
            with zipfile.ZipFile(BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > 256 or sum(m.file_size for m in members) > 10 * 1024 * 1024:
                    raise ValueError('Oversized DOCX expansion')
                if any(m.filename.startswith('word/media/') for m in members):
                    raise ValueError('Embedded visuals require separate image inputs')
                root = ElementTree.fromstring(archive.read('word/document.xml'))
                text = '\n'.join(''.join(p.itertext()) for p in root.iter()
                                 if p.tag.endswith('}p'))
            mime, coverage = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'document_body_text'
        else:
            raise InputError("Supported inputs: PNG, JPEG, WebP, UTF-8 text/Markdown/CSV, text PDF, and DOCX without embedded visuals.")
    except InputError:
        raise
    except Exception:
        raise InputError("Document cannot be completely read within the text-input limits. Use an unencrypted text document, at most 30 PDF pages, or attach visuals separately.") from None
    if not text.strip() or '\0' in text or len(text) > MAX_TEXT:
        raise InputError("Extracted document text must be nonblank and within 60,000 characters; split the document before attaching.")
    return mime, text, coverage


class ConversationAttachments(ConversationRepository):
    def __init__(self, *, database_url, storage):
        super().__init__(database_url=database_url)
        self.storage = storage

    def ensure_schema(self):
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""CREATE TABLE IF NOT EXISTS vault_private.vault_conversation_attachments (
              attachment_id text PRIMARY KEY, user_id text NOT NULL, workspace_id text NOT NULL,
              conversation_id text NOT NULL, upload_key text NOT NULL, name text NOT NULL,
              mime text NOT NULL, content_hash text NOT NULL, size_bytes integer NOT NULL,
              extracted_text text, coverage text NOT NULL, turn_id text,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE(user_id,workspace_id,conversation_id,upload_key),
              FOREIGN KEY(user_id,workspace_id,conversation_id) REFERENCES
                vault_private.vault_conversations(user_id,workspace_id,conversation_id) ON DELETE CASCADE,
              FOREIGN KEY(user_id,workspace_id,conversation_id,turn_id) REFERENCES
                vault_private.vault_conversation_turns(user_id,workspace_id,conversation_id,turn_id) ON DELETE CASCADE
            )""")

    def cleanup_expired(self):
        """Bounded retention work on staged inputs; submitted originals remain intact."""
        from types import SimpleNamespace
        from app.vault_runtime.workspace_files.errors import WorkspaceFileNotFoundError
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT attachment_id,user_id,workspace_id FROM vault_private.vault_conversation_attachments
              WHERE turn_id IS NULL AND created_at<=now()-interval '24 hours'
              ORDER BY created_at LIMIT 64 FOR UPDATE SKIP LOCKED""")
            rows=cursor.fetchall()
            for identity,user,workspace in rows:
                try:
                    self._files(SimpleNamespace(user_id=user)).delete_path(workspace_id=workspace,path=identity,recursive=False)
                except WorkspaceFileNotFoundError:
                    pass
                cursor.execute("DELETE FROM vault_private.vault_conversation_attachments WHERE attachment_id=%s",(identity,))
        return len(rows)

    def _files(self, principal):
        return WorkspaceFilesystemStore(self.storage, private_user_id=principal.user_id)

    @staticmethod
    def _view(row):
        return dict(id=row[0], name=row[1], mime=row[2], hash=row[3], size=row[4], coverage=row[5])

    def stage(self, principal, conversation_id, *, upload_key, name, data):
        if not isinstance(name, str) or not name.strip() or len(name) > 256 or '/' in name or '\\' in name:
            raise InputError("Attachment filename must be a plain name within 256 characters.")
        if not isinstance(upload_key, str) or not 1 <= len(upload_key) <= 128 or not isinstance(data, str) or len(data) > 7_000_000:
            raise InputError("Invalid attachment upload.")
        try:
            content = base64.b64decode(data, validate=True)
        except Exception:
            raise InputError("Invalid attachment bytes.") from None
        # Untrusted compressed documents must not exhaust the HTTP process.
        try:
            decoded=subprocess.run([sys.executable,'-m','app.vault_runtime.conversation.attachment_extract',name],
                input=content,capture_output=True,timeout=15,check=True)
            if len(decoded.stdout)>400000:
                raise ValueError('Extraction output budget')
            mime,text,coverage=json.loads(decoded.stdout)
        except (subprocess.SubprocessError,ValueError):
            raise InputError("Attachment cannot be safely decoded within its format, size and extraction limits.") from None
        digest = sha256(content).hexdigest()
        identity=None
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                self._header(cursor, principal, conversation_id, lock=True)
                cursor.execute("""SELECT attachment_id,name,mime,content_hash,size_bytes,coverage
                  FROM vault_private.vault_conversation_attachments
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND upload_key=%s""",
                  (*self._scope(principal, conversation_id), upload_key))
                prior = cursor.fetchone()
                if prior:
                    if prior[3] != digest or prior[1] != name:
                        raise ConflictError("Upload identity was reused with different content.")
                    return self._view(prior)
                cursor.execute("""SELECT count(*) FROM vault_private.vault_conversation_attachments
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id IS NULL""",
                  self._scope(principal, conversation_id))
                if cursor.fetchone()[0] >= MAX_FILES:
                    raise InputError("Attach at most four files per message; remove unused inputs first.")
                cursor.execute("""SELECT coalesce(sum(size_bytes),0) FROM vault_private.vault_conversation_attachments
                  WHERE user_id=%s AND workspace_id=%s""",(principal.user_id,principal.workspace_id))
                if cursor.fetchone()[0]+len(content)>100*1024*1024:
                    raise InputError("Private attachment storage limit reached (100 MiB per workspace).")
                identity = str(uuid4())
                self._files(principal).write_bytes(workspace_id=principal.workspace_id, file_key=identity, content=content)
                cursor.execute("""INSERT INTO vault_private.vault_conversation_attachments
                  (attachment_id,user_id,workspace_id,conversation_id,upload_key,name,mime,content_hash,size_bytes,extracted_text,coverage)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (identity,*self._scope(principal, conversation_id),upload_key,name,mime,digest,len(content),text,coverage))
                return self._view((identity,name,mime,digest,len(content),coverage))
        except BaseException:
            if identity is not None:
                try:
                    self._files(principal).delete_path(workspace_id=principal.workspace_id,path=identity,recursive=False)
                except Exception:
                    pass  # Original transaction error remains authoritative.
            raise

    def bind(self, cursor, principal, turn, ids):
        if not isinstance(ids, list) or len(ids) > MAX_FILES or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids):
            raise InputError("Invalid submitted attachment IDs.")
        cursor.execute("""SELECT attachment_id FROM vault_private.vault_conversation_attachments
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s ORDER BY attachment_id FOR UPDATE""",
          (*self._scope(principal,turn.conversation_id),turn.turn_id))
        bound = [r[0] for r in cursor.fetchall()]
        if bound or turn.duplicate:
            if sorted(ids) != bound:
                raise ConflictError("Submitted attachments cannot change on retry.")
            return
        for identity in ids:
            cursor.execute("""UPDATE vault_private.vault_conversation_attachments SET turn_id=%s
              WHERE attachment_id=%s AND user_id=%s AND workspace_id=%s AND conversation_id=%s
                AND turn_id IS NULL AND created_at>now()-interval '24 hours' RETURNING attachment_id""",
              (turn.turn_id,identity,*self._scope(principal,turn.conversation_id)))
            if cursor.fetchone() is None:
                raise InputError("Attachment is unavailable, expired, or already submitted.")

    def metadata(self, principal, conversation_id, turn_ids):
        if not turn_ids:
            return {}
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_authority(cursor, principal)
            self._header(cursor, principal, conversation_id, lock=False)
            cursor.execute("""SELECT attachment_id,name,mime,content_hash,size_bytes,coverage,turn_id
              FROM vault_private.vault_conversation_attachments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=ANY(%s)
              ORDER BY created_at,attachment_id""", (*self._scope(principal,conversation_id),turn_ids))
            result={}
            for row in cursor.fetchall():
                result.setdefault(row[6],[]).append(self._view(row))
            return result

    def preflight(self, principal, conversation_id, ids, provider, model):
        if not isinstance(ids,list) or len(ids)>MAX_FILES or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
            raise InputError("Invalid submitted attachment IDs.")
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            self._header(cursor,principal,conversation_id,lock=False)
            cursor.execute("""SELECT mime FROM vault_private.vault_conversation_attachments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND attachment_id=ANY(%s)
                AND turn_id IS NULL AND created_at>now()-interval '24 hours'""",
              (*self._scope(principal,conversation_id),ids))
            rows=cursor.fetchall()
        if len(rows)!=len(ids):
            raise InputError("Attachment is unavailable, expired, or already submitted.")
        if sum(1 for r in rows if r[0].startswith('image/')):
            supported=(provider=='gemini' or provider=='openai' and model.startswith(('gpt-4o','gpt-4.1','gpt-5','o3','o4'))
                or provider=='xai' and ('vision' in model or model.startswith(('grok-4','grok-2-image'))))
            if not supported:
                raise InputError("Select an image-capable model before submitting images.")

    def inputs(self, principal, turn):
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_authority(cursor, principal)
            cursor.execute("""SELECT attachment_id,name,mime,content_hash,size_bytes,coverage,extracted_text
              FROM vault_private.vault_conversation_attachments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s ORDER BY attachment_id""",
              (*self._scope(principal,turn.conversation_id),turn.turn_id))
            rows = cursor.fetchall()
        metadata, parts = [], []
        for row in rows:
            _, _, raw = self._files(principal).read_file_bytes(workspace_id=principal.workspace_id,file_key=row[0],max_bytes=MAX_FILE_BYTES)
            if sha256(raw).hexdigest() != row[3]:
                raise ConflictError("Submitted attachment bytes changed.")
            metadata.append(self._view(row))
            if row[6] is None:
                parts.append(dict(type='input_text',text=f"Untrusted image attachment {row[1]} [{row[0]}]"))
                parts.append(dict(type='input_image',image_url=f'data:{row[2]};base64,'+base64.b64encode(raw).decode()))
            else:
                parts.append(dict(type='input_text',text=f"Untrusted attachment {row[1]} [{row[0]}], coverage={row[5]}:\n{row[6]}"))
        return metadata, parts

    def learning_inputs(self, cursor, principal, conversation_id, turn_ids):
        """Original submitted inputs for both learners, under their source fence.

        The attachment ID and original byte hash remain part of every evidence
        identity. External documents never become user assertions/tool results.
        """
        self._require_authority(cursor,principal)
        cursor.execute("""SELECT attachment_id,name,mime,content_hash,size_bytes,coverage,extracted_text,turn_id
          FROM vault_private.vault_conversation_attachments
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=ANY(%s)
          ORDER BY turn_id,attachment_id FOR SHARE""",
          (*self._scope(principal,conversation_id),list(turn_ids)))
        rows=cursor.fetchall()
        if len(rows)>16 or sum(row[4] for row in rows)>20*1024*1024:
            raise ConflictError('Attachment learning exceeds the original-input budget.')
        sources,parts,metadata=[],[],{}
        for row in rows:
            identity,name,mime,digest,size,coverage,text,turn_id=row
            _,_,raw=self._files(principal).read_file_bytes(workspace_id=principal.workspace_id,
                file_key=identity,max_bytes=MAX_FILE_BYTES)
            if len(raw)!=size or sha256(raw).hexdigest()!=digest:
                raise ConflictError('Original attachment evidence changed.')
            # Repeat the SAME bounded decoder, so cached extraction metadata
            # cannot be mistaken for the actual original file's content.
            decoded=subprocess.run([sys.executable,'-m','app.vault_runtime.conversation.attachment_extract',name],
                input=raw,capture_output=True,timeout=15,check=True)
            if len(decoded.stdout)>400000 or json.loads(decoded.stdout)!=[mime,text,coverage]:
                raise ConflictError('Original attachment extraction changed.')
            source_id='attachment:'+identity+':'+digest
            label=f'Untrusted original attachment {name}; coverage={coverage}; sourceId={source_id}'
            sources.append((source_id,'document',label+'\n'+text if text is not None else label))
            if text is None:
                parts.extend([dict(type='input_text',text=label),dict(type='input_image',
                    image_url=f'data:{mime};base64,'+base64.b64encode(raw).decode())])
            metadata.setdefault(turn_id,[]).append(self._view(row[:7]))
        return sources,parts,metadata

    def remove(self, principal, conversation_id, identity):
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            self._header(cursor,principal,conversation_id,lock=True)
            cursor.execute("""DELETE FROM vault_private.vault_conversation_attachments
              WHERE attachment_id=%s AND user_id=%s AND workspace_id=%s AND conversation_id=%s
                AND turn_id IS NULL RETURNING attachment_id""",(identity,*self._scope(principal,conversation_id)))
            if cursor.fetchone() is None:
                raise InputError("Only an owned unsubmitted attachment can be removed.")
            self._files(principal).delete_path(workspace_id=principal.workspace_id,path=identity,recursive=False)
