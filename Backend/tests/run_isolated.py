"""Run regression tests without importing developer cloud/model credentials."""
import os
from pathlib import Path
import sys
import tempfile


def main():
    backend=Path(__file__).resolve().parents[1]
    scratch=Path(tempfile.mkdtemp(prefix='gongmingbai-tests-')).resolve()
    assert scratch.is_relative_to(Path(tempfile.gettempdir()).resolve())
    os.environ.update(SUPABASE_URL='', SUPABASE_SECRET_KEY='', SUPABASE_PUBLISHABLE_KEY='',
        DASHSCOPE_API_KEY='', APP_ENV='development', DATA_DIR=str(scratch/'bootstrap'))
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(backend),str(backend/'tests')]
    import pytest
    print('Isolated regression: cloud/model credentials disabled. Temporary data:',scratch)
    return pytest.main([str(backend/'tests'),'-q','-p','no:cacheprovider','--basetemp',str(scratch/'cases')])


if __name__=='__main__':raise SystemExit(main())
