import os
import unittest


class DevBatTest(unittest.TestCase):
    """개발용 실행.bat 은 사용자가 따로 받아 쓰는 파일이라 깨지면 바로 눈에 띈다."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, '개발용 실행.bat'), 'rb') as source:
            cls.raw = source.read()
        cls.text = cls.raw.decode('utf-8')

    def test_download_does_not_draw_a_progress_bar(self):
        """PowerShell 진행 막대가 Windows Terminal 에서 이미 찍은 한글을 겹쳐 두 번씩 보이게 했다."""
        self.assertIn("$ProgressPreference='SilentlyContinue'", self.text)
        self.assertLess(self.text.index("$ProgressPreference"), self.text.index('Invoke-WebRequest'))
        self.assertLess(self.text.index("$ProgressPreference"), self.text.index('Expand-Archive'))

    def test_line_endings_and_encoding_stay_safe(self):
        self.assertNotIn(b'\n', self.raw.replace(b'\r\n', b''), '줄 끝은 CRLF 여야 합니다')
        self.assertFalse(self.raw.startswith(b'\xef\xbb\xbf'), 'BOM 이 있으면 첫 줄이 깨집니다')
        self.assertIn('chcp 65001', self.text)


if __name__ == '__main__':
    unittest.main()
