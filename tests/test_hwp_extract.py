import sys
import types
import unittest
from unittest import mock

import hwp_extract


class HwpCleanupTest(unittest.TestCase):
    def test_com_object_is_closed_when_text_extraction_fails(self):
        """텍스트를 읽다 실패해도 백그라운드 한글 프로세스를 닫는다."""
        hwp = mock.MagicMock()
        hwp.GetTextFile.side_effect = RuntimeError('읽기 실패')

        client = types.ModuleType('win32com.client')
        client.gencache = types.SimpleNamespace(EnsureDispatch=lambda _name: hwp)
        win32com = types.ModuleType('win32com')
        win32com.client = client

        with mock.patch.dict(
                sys.modules,
                {'win32com': win32com, 'win32com.client': client}):
            self.assertEqual(hwp_extract._hwp_win32com('broken.hwp'), '')

        hwp.Quit.assert_called_once_with()

    def test_ole_file_is_closed_when_body_reading_fails(self):
        """OLE 본문을 읽다 실패해도 열린 파일 핸들을 닫는다."""
        ole = mock.MagicMock()
        ole.openstream.side_effect = RuntimeError('읽기 실패')
        olefile = types.ModuleType('olefile')
        olefile.OleFileIO = lambda _path: ole

        with mock.patch.dict(sys.modules, {'olefile': olefile}):
            self.assertEqual(hwp_extract._hwp_olefile('broken.hwp'), '')

        ole.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
