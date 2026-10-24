import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            'timestamp': datetime.now(UTC).isoformat().replace('+00:00','Z'),
            'event': getattr(record, 'event', record.name),
            'level': record.levelname.lower(),
            'user_id': getattr(record, 'user_id', None),
            'email': getattr(record, 'email', None),
            'role': getattr(record, 'role', None),
            'ip': getattr(record, 'ip', None),
            'path': getattr(record, 'path', None),
            'method': getattr(record, 'method', None),
            'user_agent': getattr(record, 'user_agent', None),
            'app': 'merchku',
            'env': os.getenv('ENV','dev') or os.getenv('FLASK_ENV','dev'),
            'msg': record.getMessage(),
        }
        if record.exc_info:
            log['exc_info'] = self.formatException(record.exc_info)
        # merge extra safely
        for k,v in record.__dict__.items():
            if k not in log and not k.startswith('_') and k not in ('name','msg','args','levelname','levelno','pathname','filename','module','exc_info','exc_text','stack_info','lineno','funcName','created','msecs','relativeCreated','thread','threadName','processName','process'):
                try:
                    json.dumps({k:v})
                    log[k]=v
                except Exception:  # nosec B110 - field tambahan yang tidak serializable diabaikan
                    pass
        return json.dumps(log, ensure_ascii=False)

def setup_security_logger(app=None):
    logger = logging.getLogger('security')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    log_dir = os.getenv('LOG_DIR','logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir,'security.json')
    fh = RotatingFileHandler(log_path, maxBytes=int(os.getenv('LOG_MAX_BYTES','10485760')), backupCount=int(os.getenv('LOG_BACKUP_COUNT','5')), encoding='utf-8')
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)
    # stdout
    sh = logging.StreamHandler()
    sh.setFormatter(JsonFormatter())
    logger.addHandler(sh)
    return logger

def sec_log(**kwargs):
    """Catat event keamanan ke log JSON.

    Fungsi ini WAJIB tidak pernah melempar exception: logging yang gagal
    tidak boleh menjatuhkan request. Semua error ditelan di sini.
    """
    try:
        lg = logging.getLogger('security')
        extra = {}
        for k, v in kwargs.items():
            if v is not None:
                extra[k] = v
        # level khusus dipakai memilih level log, bukan field biasa
        lvl = extra.pop('level', 'info')
        # isi konteks request & user secara otomatis bila tersedia
        try:
            from flask import has_request_context, request
            from flask_login import current_user

            if has_request_context():
                extra.setdefault('path', request.path)
                extra.setdefault('method', request.method)
                extra.setdefault('user_agent', request.user_agent.string or None)
                if current_user.is_authenticated:
                    extra.setdefault('user_id', current_user.id)
                    extra.setdefault('email', current_user.email)
                    extra.setdefault('role', current_user.role)
        except Exception:  # nosec B110 - logging tidak boleh gagal karena konteks request
            pass
        fn = getattr(lg, lvl, lg.info)
        fn(extra.get('event', 'event'), extra=extra)
    except Exception:  # nosec B110 - logging tidak boleh menggagalkan request
        pass
